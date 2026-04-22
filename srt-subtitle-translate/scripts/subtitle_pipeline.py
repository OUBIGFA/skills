#!/usr/bin/env python3
"""Orchestrate end-to-end subtitle translation preparation, finalize, and cleanup."""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from chunk_srt import split_command as chunk_split_command, merge_command as chunk_merge_command
from detect_clause_rebalance import detect_candidates as detect_clause_rebalance_candidates
from detect_orphan_tails import detect_candidates as detect_orphan_tail_candidates
from extract_subtitle_terms import collect_candidates, read_blocks as read_blocks_for_terms
from preprocess_srt import (
    drop_empty_blocks,
    parse_blocks,
    parse_timestamp_range,
    render_blocks,
    renumber_blocks,
)


def default_final_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}-CN{input_path.suffix}")


def default_preprocessed_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.preprocessed{input_path.suffix}")


def default_terms_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.terms.json")


def default_orphan_tails_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.orphan-tails.json")


def default_clause_rebalance_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.clause-rebalance.json")


def default_chunk_dir(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.chunks")


def default_pipeline_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.pipeline.json")


def default_draft_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.draft-CN{input_path.suffix}")


def cleanup_skill_cache() -> None:
    skill_cache = Path(__file__).resolve().parent / "__pycache__"
    if skill_cache.exists():
        shutil.rmtree(skill_cache, ignore_errors=True)


PIPELINE_STAGES = (
    "prepared",
    "translated",
    "review_polished",
    "finalized",
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def allowed_next_actions_for_stage(*, direct_translate: bool, stage: str) -> list[str]:
    if stage == "prepared":
        return (
            [
                "review_segmentation_in_main_conversation",
                "translate_fullfile_in_main_conversation",
                "mark_translated_stage",
            ]
            if direct_translate
            else [
                "review_segmentation_in_main_conversation",
                "translate_chunk_in_main_conversation",
                "resume_next_unfinished_chunk",
                "mark_translated_stage",
            ]
        )

    if stage == "translated":
        actions = ["review_and_polish_in_main_conversation", "mark_review_polished_stage"]
        if not direct_translate:
            actions.insert(0, "merge_chunk_drafts")
        return actions

    if stage == "review_polished":
        return ["write_formal_final_output", "mark_finalized_stage"]

    return []


def update_pipeline_stage(payload: dict[str, object], stage: str) -> dict[str, object]:
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Unsupported stage: {stage}")

    stage_order = {name: index for index, name in enumerate(PIPELINE_STAGES)}
    direct_translate = payload.get("manifest") is None

    payload["current_stage"] = stage
    payload["allowed_next_actions"] = allowed_next_actions_for_stage(
        direct_translate=direct_translate,
        stage=stage,
    )

    stage_timestamps = payload.get("stage_timestamps")
    if not isinstance(stage_timestamps, dict):
        stage_timestamps = {}
    timestamp = now_iso()
    for name in PIPELINE_STAGES:
        if stage_order[name] <= stage_order[stage]:
            stage_timestamps.setdefault(name, timestamp if name == stage else None)
    stage_timestamps[stage] = timestamp
    payload["stage_timestamps"] = stage_timestamps
    return payload


def load_pipeline_payload(pipeline_path: Path) -> dict[str, object]:
    return json.loads(pipeline_path.read_text(encoding="utf-8"))


def save_pipeline_payload(pipeline_path: Path, payload: dict[str, object]) -> None:
    pipeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def runtime_minutes_for_blocks(blocks: list[tuple[str, str, list[str]]]) -> float:
    if not blocks:
        return 0.0
    start_ms, _ = parse_timestamp_range(blocks[0][1])
    _, end_ms = parse_timestamp_range(blocks[-1][1])
    return max(0.0, (end_ms - start_ms) / 60000)


def run_preprocess(input_path: Path, output_path: Path) -> int:
    content = input_path.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(content)
    blocks = drop_empty_blocks(blocks)
    blocks = renumber_blocks(blocks)
    output_path.write_text(render_blocks(blocks, keep_line_breaks=False), encoding="utf-8", newline="\n")
    return len(blocks)


def run_extract_terms(input_path: Path, output_path: Path) -> int:
    blocks = read_blocks_for_terms(input_path)
    payload = {
        "source": str(input_path),
        "term_count": 0,
        "terms": collect_candidates(blocks),
    }
    payload["term_count"] = len(payload["terms"])
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return int(payload["term_count"])


def run_detect_orphan_tails(input_path: Path, output_path: Path) -> int:
    content = input_path.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(content)
    candidates = detect_orphan_tail_candidates(
        blocks,
        max_tail_duration_ms=2000,
        max_tail_words=4,
        max_gap_ms=500,
    )
    payload = {
        "source": str(input_path),
        "total_blocks": len(blocks),
        "candidate_count": len(candidates),
        "thresholds": {
            "max_tail_duration_ms": 2000,
            "max_tail_words": 4,
            "max_gap_ms": 500,
        },
        "policy": (
            "Report-only. The model decides whether to merge each candidate during "
            "preprocessing. After any merge, combine timestamps (start of A, end of B), "
            "join the text, and renumber the whole subtitle sequentially from 1."
        ),
        "candidates": candidates,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return len(candidates)


def run_detect_clause_rebalance(input_path: Path, output_path: Path) -> int:
    content = input_path.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(content)
    candidates = detect_clause_rebalance_candidates(
        blocks,
        max_gap_ms=500,
        min_tail_words_for_b=5,
        min_prev_words_after_cut=3,
    )
    payload = {
        "source": str(input_path),
        "total_blocks": len(blocks),
        "candidate_count": len(candidates),
        "thresholds": {
            "max_gap_ms": 500,
            "min_tail_words_for_b": 5,
            "min_prev_words_after_cut": 3,
        },
        "policy": (
            "Report-only. The model decides whether and where to rebalance each "
            "candidate during preprocessing. For every accepted candidate, shift "
            "the dangling tail forward into cue B at the semantic hinge, "
            "redistribute the combined timestamp proportionally across "
            "[start_of_A, end_of_B], preserve both cues (do NOT merge), and "
            "renumber the whole subtitle sequentially from 1 after all edits."
        ),
        "candidates": candidates,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return len(candidates)


def write_pipeline_file(
    pipeline_path: Path,
    *,
    source: Path,
    preprocessed: Path,
    terms: Path,
    orphan_tails: Path,
    orphan_tail_count: int,
    clause_rebalance: Path,
    clause_rebalance_count: int,
    chunk_dir: Path | None,
    manifest: Path | None,
    final_output: Path,
    chunk_count: int,
    total_blocks: int,
    runtime_minutes: float,
    direct_translate: bool,
) -> None:
    manifest_json = json.loads(manifest.read_text(encoding="utf-8")) if manifest else {"chunks": []}
    payload = {
        "source": str(source),
        "preprocessed": str(preprocessed),
        "terms": str(terms),
        "orphan_tails_report": str(orphan_tails),
        "orphan_tail_candidate_count": orphan_tail_count,
        "clause_rebalance_report": str(clause_rebalance),
        "clause_rebalance_candidate_count": clause_rebalance_count,
        "chunk_dir": str(chunk_dir) if chunk_dir else None,
        "manifest": str(manifest) if manifest else None,
        "final_output": str(final_output),
        "chunk_count": chunk_count,
        "total_blocks": total_blocks,
        "runtime_minutes": runtime_minutes,
        "translation_mode": {
            "preferred": "direct_fullfile" if direct_translate else "sequential_main_thread_chunks",
            "fallback": "sequential_main_thread_chunks",
        },
        "current_stage": "prepared",
        "allowed_next_actions": [],
        "stage_timestamps": {},
        "execution_constraints": {
            "translation_executor": "main_model_only",
            "segmentation_review_executor": "main_model_only",
            "final_review_executor": "main_model_only",
            "translator_discovery_forbidden": True,
            "default_parallel_subagents_forbidden": True,
            "translated_file_structure_locked": True,
            "translated_file_contract": (
                "Every in-progress translated file must preserve exactly the same cue numbers, "
                "timestamps, cue order, and block count as its paired source file. Only subtitle text may change."
            ),
            "forbidden_actions": [
                "search_for_existing_translators",
                "probe_local_translation_tools",
                "probe_translation_packages",
                "install_translation_packages",
                "use_browser_translation_workflows",
                "use_external_translation_apis",
                "use_translation_websites",
                "search_for_existing_subtitles",
                "probe_local_llm_wrappers",
                "probe_local_api_relays",
            ],
            "required_next_step": (
                "The main model must review segmentation, translate, and complete the final review/polish. "
                "Use local scripts only for preprocessing, optional report-only hints, chunk orchestration, validation, merge, and cleanup."
            ),
            "final_output_guard": (
                "Formal -CN output is not complete until the main conversation has finished the final review and polish pass."
            ),
        },
        "work_items": [
            {
                "chunk_index": item["index"],
                "source_file": str(chunk_dir / item["source_file"]) if chunk_dir else str(preprocessed),
                "translated_file": str(chunk_dir / item["translated_file"]) if chunk_dir else str(final_output),
                "start_cue": item["start_cue"],
                "end_cue": item["end_cue"],
                "block_count": item["block_count"],
            }
            for item in manifest_json["chunks"]
        ],
    }
    if direct_translate:
        payload["work_items"] = [
            {
                "chunk_index": 1,
                "source_file": str(preprocessed),
                "translated_file": str(final_output),
                "start_cue": 1,
                "end_cue": total_blocks,
                "block_count": total_blocks,
            }
        ]
    update_pipeline_stage(payload, "prepared")
    save_pipeline_payload(pipeline_path, payload)


def prepare_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    preprocessed_path = Path(args.preprocessed) if args.preprocessed else default_preprocessed_output(input_path)
    terms_path = Path(args.terms) if args.terms else default_terms_output(input_path)
    orphan_tails_path = Path(args.orphan_tails) if args.orphan_tails else default_orphan_tails_output(input_path)
    clause_rebalance_path = Path(args.clause_rebalance) if args.clause_rebalance else default_clause_rebalance_output(input_path)
    chunk_dir = Path(args.chunk_dir) if args.chunk_dir else default_chunk_dir(input_path)
    pipeline_path = Path(args.pipeline) if args.pipeline else default_pipeline_output(input_path)
    final_output = Path(args.output) if args.output else default_final_output(input_path)

    total_blocks = run_preprocess(
        input_path,
        preprocessed_path,
    )
    term_count = run_extract_terms(preprocessed_path, terms_path)
    orphan_tail_count = run_detect_orphan_tails(preprocessed_path, orphan_tails_path)
    clause_rebalance_count = run_detect_clause_rebalance(preprocessed_path, clause_rebalance_path)
    preprocessed_blocks = parse_blocks(preprocessed_path.read_text(encoding="utf-8-sig"))
    runtime_minutes = runtime_minutes_for_blocks(preprocessed_blocks)

    direct_translate = runtime_minutes <= 30.0 and not args.force_chunk

    manifest_path: Path | None = None
    manifest_json = {"chunk_count": 0}
    if not direct_translate:
        split_args = argparse.Namespace(
            input=str(preprocessed_path),
            output_dir=str(chunk_dir),
            target_minutes=args.target_minutes,
        )
        split_status = chunk_split_command(split_args)
        if split_status != 0:
            return split_status
        manifest_path = chunk_dir / "manifest.json"
        manifest_json = json.loads(manifest_path.read_text(encoding="utf-8"))

    write_pipeline_file(
        pipeline_path,
        source=input_path,
        preprocessed=preprocessed_path,
        terms=terms_path,
        orphan_tails=orphan_tails_path,
        orphan_tail_count=orphan_tail_count,
        clause_rebalance=clause_rebalance_path,
        clause_rebalance_count=clause_rebalance_count,
        chunk_dir=chunk_dir if not direct_translate else None,
        manifest=manifest_path,
        final_output=final_output,
        chunk_count=int(manifest_json["chunk_count"]) if not direct_translate else 0,
        total_blocks=total_blocks,
        runtime_minutes=runtime_minutes,
        direct_translate=direct_translate,
    )

    print(f"[OK] Prepared subtitle pipeline")
    print(f"[OK] Preprocessed: {preprocessed_path}")
    print(f"[OK] Terms: {terms_path} ({term_count} candidates)")
    print(f"[OK] Orphan-tail report: {orphan_tails_path} ({orphan_tail_count} candidates)")
    print(f"[OK] Clause-rebalance report: {clause_rebalance_path} ({clause_rebalance_count} candidates)")
    if orphan_tail_count:
        print("[HINT] Optional: review the orphan-tail report during semantic segmentation review")
    if clause_rebalance_count:
        print("[HINT] Optional: review the clause-rebalance report during semantic segmentation review")
    if direct_translate:
        print(f"[OK] Direct full-file translation recommended")
        print("[OK] Main conversation must perform segmentation review, translation, and final polish before formal delivery")
    else:
        print(f"[OK] Chunks: {chunk_dir}")
        print("[OK] Next step is sequential chunk translation in the main conversation; default parallel subagents are not part of this workflow")
        print("[OK] Each NNN.translated.srt must keep exactly the same cue numbers and timestamps as its paired NNN.source.srt")
    print(f"[OK] Pipeline: {pipeline_path}")
    print(f"[OK] Final output target: {final_output}")
    cleanup_skill_cache()
    return 0


def finalize_command(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    payload = load_pipeline_payload(pipeline_path)
    manifest_value = payload.get("manifest")
    if not manifest_value:
        print("[ERROR] This pipeline is configured for direct full-file translation and does not use finalize.", file=sys.stderr)
        return 1

    manifest = Path(manifest_value)
    configured_final_output = Path(args.output) if args.output else Path(payload["final_output"])
    source_path = Path(payload["source"])
    draft_output = default_draft_output(source_path)
    merge_output = configured_final_output if args.reviewed else draft_output

    merge_args = argparse.Namespace(
        manifest=str(manifest),
        output=str(merge_output),
    )
    status = chunk_merge_command(merge_args)
    if status != 0:
        return status

    if not args.reviewed:
        update_pipeline_stage(payload, "translated")
        save_pipeline_payload(pipeline_path, payload)
        print(f"[OK] Merged translated chunks into a draft subtitle: {draft_output}")
        print(f"[OK] Formal final output not written yet: {configured_final_output}")
        print("[OK] Main-conversation review and polish is still required before final completion")
        return 0

    update_pipeline_stage(payload, "review_polished")
    save_pipeline_payload(pipeline_path, payload)

    if not args.keep_intermediates:
        cleanup_paths = [
            Path(payload["preprocessed"]),
            Path(payload["terms"]),
            Path(payload.get("orphan_tails_report", "")) if payload.get("orphan_tails_report") else None,
            Path(payload.get("clause_rebalance_report", "")) if payload.get("clause_rebalance_report") else None,
            Path(payload["chunk_dir"]),
            pipeline_path,
        ]
        for path in cleanup_paths:
            if path is None:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        cleanup_skill_cache()
        print("[OK] Cleaned intermediate resources")

    payload = update_pipeline_stage(payload, "finalized")
    if args.keep_intermediates:
        save_pipeline_payload(pipeline_path, payload)
    print(f"[OK] Formal final subtitle written: {configured_final_output}")
    return 0


def set_stage_command(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    payload = load_pipeline_payload(pipeline_path)
    stage = args.stage
    try:
        update_pipeline_stage(payload, stage)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    save_pipeline_payload(pipeline_path, payload)
    print(f"[OK] Updated pipeline stage: {stage}")
    timestamps = payload.get("stage_timestamps", {})
    if isinstance(timestamps, dict) and stage in timestamps:
        print(f"[OK] Stage timestamp: {timestamps[stage]}")
    return 0


def clean_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    targets = [
        default_preprocessed_output(input_path),
        default_terms_output(input_path),
        default_orphan_tails_output(input_path),
        default_clause_rebalance_output(input_path),
        default_chunk_dir(input_path),
        default_pipeline_output(input_path),
    ]
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
    cleanup_skill_cache()
    print("[OK] Cleaned default intermediate resources")
    return 0


def status_command(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    payload = load_pipeline_payload(pipeline_path)
    print(f"[OK] Source: {payload['source']}")
    print(f"[OK] Stage: {payload.get('current_stage', 'unknown')}")
    print(f"[OK] Runtime minutes: {payload.get('runtime_minutes', 0)}")
    print(f"[OK] Final output: {payload['final_output']}")
    mode = payload.get("translation_mode", {}).get("preferred", "unknown")
    print(f"[OK] Translation mode: {mode}")
    allowed = payload.get("allowed_next_actions", [])
    if allowed:
        print(f"[OK] Allowed next actions: {', '.join(allowed)}")
    timestamps = payload.get("stage_timestamps", {})
    if isinstance(timestamps, dict):
        completed = [f"{stage}={timestamps[stage]}" for stage in PIPELINE_STAGES if timestamps.get(stage)]
        if completed:
            print(f"[OK] Stage timestamps: {', '.join(completed)}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare, finalize, and clean a subtitle translation pipeline with chunk metadata.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Normalize subtitle text, extract terms, split chunks, and write pipeline metadata")
    prepare.add_argument("input", help="Path to the source subtitle file")
    prepare.add_argument("--output", help="Optional final output subtitle path")
    prepare.add_argument("--preprocessed", help="Optional intermediate preprocessed subtitle path")
    prepare.add_argument("--terms", help="Optional term JSON path")
    prepare.add_argument("--orphan-tails", dest="orphan_tails", help="Optional orphan-tail candidate report JSON path")
    prepare.add_argument("--clause-rebalance", dest="clause_rebalance", help="Optional clause-rebalance candidate report JSON path")
    prepare.add_argument("--chunk-dir", help="Optional chunk directory path")
    prepare.add_argument("--pipeline", help="Optional pipeline JSON path")
    prepare.add_argument("--target-minutes", type=float, default=20.0, help="Target runtime minutes per chunk when chunking is required")
    prepare.add_argument("--force-chunk", action="store_true", help="Force chunking even when the runtime would otherwise stay on the direct full-file path")
    prepare.set_defaults(func=prepare_command)

    finalize = subparsers.add_parser("finalize", help="Merge translated chunks into a draft subtitle by default, or write the formal final subtitle after review")
    finalize.add_argument("pipeline", help="Path to the pipeline JSON written by prepare")
    finalize.add_argument("--output", help="Optional final output subtitle path override")
    finalize.add_argument("--reviewed", action="store_true", help="Confirm that the mandatory post-merge review/polish in the main conversation has been completed; without this flag, finalize writes only a draft subtitle")
    finalize.add_argument("--keep-intermediates", action="store_true", help="Keep preprocessed, terms, chunk dir, and pipeline metadata")
    finalize.set_defaults(func=finalize_command)

    clean = subparsers.add_parser("clean", help="Delete the default intermediate files for a source subtitle")
    clean.add_argument("input", help="Path to the source subtitle file")
    clean.set_defaults(func=clean_command)

    set_stage = subparsers.add_parser("set-stage", help="Persist the current pipeline stage after main-conversation work")
    set_stage.add_argument("pipeline", help="Path to the pipeline JSON")
    set_stage.add_argument("stage", choices=PIPELINE_STAGES, help="One of: prepared, translated, review_polished, finalized")
    set_stage.set_defaults(func=set_stage_command)

    status = subparsers.add_parser("status", help="Print the pipeline JSON for inspection")
    status.add_argument("pipeline", help="Path to the pipeline JSON")
    status.set_defaults(func=status_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
