#!/usr/bin/env python3
"""Orchestrate end-to-end subtitle translation preparation, finalize, and cleanup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from chunk_srt import split_command as chunk_split_command, merge_command as chunk_merge_command
from extract_subtitle_terms import main as _unused_extract_main  # noqa: F401
from extract_subtitle_terms import collect_candidates, read_blocks as read_blocks_for_terms
from preprocess_srt import main as _unused_preprocess_main  # noqa: F401
from preprocess_srt import (
    drop_empty_blocks,
    parse_blocks,
    parse_timestamp_range,
    resegment_blocks,
    render_blocks,
    renumber_blocks,
    split_overlong_blocks,
)


def default_final_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}-CN{input_path.suffix}")


def default_preprocessed_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.preprocessed{input_path.suffix}")


def default_terms_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.terms.json")


def default_chunk_dir(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.chunks")


def default_pipeline_output(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.pipeline.json")


def runtime_minutes_for_blocks(blocks: list[tuple[str, str, list[str]]]) -> float:
    if not blocks:
        return 0.0
    start_ms, _ = parse_timestamp_range(blocks[0][1])
    _, end_ms = parse_timestamp_range(blocks[-1][1])
    return max(0.0, (end_ms - start_ms) / 60000)


def run_preprocess(input_path: Path, output_path: Path, resegment_sentences: bool, max_chars: int) -> int:
    content = input_path.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(content)
    if resegment_sentences:
        blocks = resegment_blocks(blocks)
    blocks = split_overlong_blocks(blocks, max_chars=max_chars)
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


def write_pipeline_file(
    pipeline_path: Path,
    *,
    source: Path,
    preprocessed: Path,
    terms: Path,
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
        "chunk_dir": str(chunk_dir) if chunk_dir else None,
        "manifest": str(manifest) if manifest else None,
        "final_output": str(final_output),
        "chunk_count": chunk_count,
        "total_blocks": total_blocks,
        "runtime_minutes": runtime_minutes,
        "translation_mode": {
            "preferred": "direct_fullfile" if direct_translate else "parallel_subagents",
            "fallback": "direct_fullfile" if direct_translate else "sequential_chunks",
        },
        "current_stage": "ready_for_model_translation",
        "allowed_next_actions": (
            ["translate_fullfile_with_model", "write_final_output", "run_final_review"]
            if direct_translate
            else ["translate_chunk_with_model", "resume_next_unfinished_chunk", "merge_translated_chunks"]
        ),
        "execution_constraints": {
            "translation_executor": "model_only",
            "translator_discovery_forbidden": True,
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
                "Translate the subtitle text directly with the model. "
                "Use local scripts only for preprocessing, chunk orchestration, validation, merge, and cleanup."
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
    pipeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def prepare_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    preprocessed_path = Path(args.preprocessed) if args.preprocessed else default_preprocessed_output(input_path)
    terms_path = Path(args.terms) if args.terms else default_terms_output(input_path)
    chunk_dir = Path(args.chunk_dir) if args.chunk_dir else default_chunk_dir(input_path)
    pipeline_path = Path(args.pipeline) if args.pipeline else default_pipeline_output(input_path)
    final_output = Path(args.output) if args.output else default_final_output(input_path)

    total_blocks = run_preprocess(
        input_path,
        preprocessed_path,
        resegment_sentences=args.resegment_sentences,
        max_chars=args.max_chars,
    )
    term_count = run_extract_terms(preprocessed_path, terms_path)
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
    if direct_translate:
        print(f"[OK] Direct full-file translation recommended")
        print("[OK] Translation must preserve the preprocessed cue numbering and timestamps until final completion")
    else:
        print(f"[OK] Chunks: {chunk_dir}")
        print("[OK] Next step is model-driven chunk translation only; translator discovery is forbidden")
        print("[OK] Each NNN.translated.srt must keep exactly the same cue numbers and timestamps as its paired NNN.source.srt")
    print(f"[OK] Pipeline: {pipeline_path}")
    print(f"[OK] Final output target: {final_output}")
    return 0


def finalize_command(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    manifest_value = payload.get("manifest")
    if not manifest_value:
        print("[ERROR] This pipeline is configured for direct full-file translation and does not use finalize.", file=sys.stderr)
        return 1

    manifest = Path(manifest_value)
    final_output = Path(args.output) if args.output else Path(payload["final_output"])

    merge_args = argparse.Namespace(
        manifest=str(manifest),
        output=str(final_output),
    )
    status = chunk_merge_command(merge_args)
    if status != 0:
        return status

    if not args.reviewed:
        print("[OK] Merged translated chunks into a draft final subtitle")
        print("[OK] Master-pass review is still required before cleanup and final completion")
        return 0

    if not args.keep_intermediates:
        cleanup_paths = [
            Path(payload["preprocessed"]),
            Path(payload["terms"]),
            Path(payload["chunk_dir"]),
            pipeline_path,
        ]
        for path in cleanup_paths:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        print("[OK] Cleaned intermediate resources")

    return 0


def clean_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    targets = [
        default_preprocessed_output(input_path),
        default_terms_output(input_path),
        default_chunk_dir(input_path),
        default_pipeline_output(input_path),
    ]
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
    print("[OK] Cleaned default intermediate resources")
    return 0


def status_command(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    print(f"[OK] Source: {payload['source']}")
    print(f"[OK] Stage: {payload.get('current_stage', 'unknown')}")
    print(f"[OK] Runtime minutes: {payload.get('runtime_minutes', 0)}")
    print(f"[OK] Final output: {payload['final_output']}")
    mode = payload.get("translation_mode", {}).get("preferred", "unknown")
    print(f"[OK] Translation mode: {mode}")
    allowed = payload.get("allowed_next_actions", [])
    if allowed:
        print(f"[OK] Allowed next actions: {', '.join(allowed)}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare, finalize, and clean a subtitle translation pipeline with chunk metadata.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Preprocess, extract terms, split chunks, and write pipeline metadata")
    prepare.add_argument("input", help="Path to the source subtitle file")
    prepare.add_argument("--output", help="Optional final output subtitle path")
    prepare.add_argument("--preprocessed", help="Optional intermediate preprocessed subtitle path")
    prepare.add_argument("--terms", help="Optional term JSON path")
    prepare.add_argument("--chunk-dir", help="Optional chunk directory path")
    prepare.add_argument("--pipeline", help="Optional pipeline JSON path")
    prepare.add_argument("--resegment-sentences", action="store_true", help="Enable local sentence-boundary repair during preprocessing")
    prepare.add_argument("--max-chars", type=int, default=42, help="Target source cue readability limit during preprocessing")
    prepare.add_argument("--target-minutes", type=float, default=20.0, help="Target runtime minutes per chunk when chunking is required")
    prepare.add_argument("--force-chunk", action="store_true", help="Force chunking even when the runtime would otherwise stay on the direct full-file path")
    prepare.set_defaults(func=prepare_command)

    finalize = subparsers.add_parser("finalize", help="Merge translated chunks into the final subtitle and optionally clean intermediates")
    finalize.add_argument("pipeline", help="Path to the pipeline JSON written by prepare")
    finalize.add_argument("--output", help="Optional final output subtitle path override")
    finalize.add_argument("--reviewed", action="store_true", help="Confirm that the mandatory post-merge master-pass review has been completed; without this flag, finalize only merges and keeps intermediates")
    finalize.add_argument("--keep-intermediates", action="store_true", help="Keep preprocessed, terms, chunk dir, and pipeline metadata")
    finalize.set_defaults(func=finalize_command)

    clean = subparsers.add_parser("clean", help="Delete the default intermediate files for a source subtitle")
    clean.add_argument("input", help="Path to the source subtitle file")
    clean.set_defaults(func=clean_command)

    status = subparsers.add_parser("status", help="Print the pipeline JSON for inspection")
    status.add_argument("pipeline", help="Path to the pipeline JSON")
    status.set_defaults(func=status_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
