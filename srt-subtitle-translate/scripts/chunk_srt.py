#!/usr/bin/env python3
"""Split large SRT-like subtitle files into stable translation chunks and merge them back."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from preprocess_srt import TERMINAL_PUNCTUATION, parse_blocks, parse_timestamp_range, render_blocks


def read_blocks(path: Path) -> list[tuple[str, str, list[str]]]:
    content = path.read_text(encoding="utf-8-sig")
    return parse_blocks(content)


def validate_translated_chunk(
    source_blocks: list[tuple[str, str, list[str]]],
    translated_blocks: list[tuple[str, str, list[str]]],
    chunk_index: int,
) -> tuple[bool, str | None]:
    expected = len(source_blocks)
    actual = len(translated_blocks)
    if actual != expected:
        return False, f"Chunk {chunk_index:03d} block count mismatch: expected {expected}, got {actual}"

    for position, (source_block, translated_block) in enumerate(zip(source_blocks, translated_blocks), start=1):
        source_cue, source_timestamp, _ = source_block
        translated_cue, translated_timestamp, _ = translated_block

        if translated_cue != source_cue:
            return (
                False,
                (
                    f"Chunk {chunk_index:03d} cue mismatch at block {position}: "
                    f"expected cue {source_cue}, got {translated_cue}. "
                    "Translated chunks must keep exactly the same cue numbers as their paired source chunks."
                ),
            )

        if translated_timestamp != source_timestamp:
            return (
                False,
                (
                    f"Chunk {chunk_index:03d} timestamp mismatch at cue {source_cue}: "
                    f"expected {source_timestamp}, got {translated_timestamp}. "
                    "Translated chunks must keep exactly the same timestamps as their paired source chunks."
                ),
            )

    return True, None


def block_text(block: tuple[str, str, list[str]]) -> str:
    _, _, lines = block
    return " ".join(line.strip() for line in lines if line.strip()).strip()


def is_natural_boundary(
    previous_block: tuple[str, str, list[str]],
    next_block: tuple[str, str, list[str]] | None,
) -> bool:
    text = block_text(previous_block)
    if text and text.rstrip()[-1] in TERMINAL_PUNCTUATION:
        return True
    if next_block is None:
        return True

    _, prev_end = parse_timestamp_range(previous_block[1])
    next_start, _ = parse_timestamp_range(next_block[1])
    return (next_start - prev_end) >= 400


def choose_split_index(
    chunk: list[tuple[str, str, list[str]]],
    target_ms: int,
) -> int:
    if len(chunk) <= 1:
        return 1

    start_ms, _ = parse_timestamp_range(chunk[0][1])
    best_index = len(chunk) - 1
    best_score: float | None = None
    min_index = max(1, round(len(chunk) * 0.6))

    for index in range(min_index, len(chunk)):
        previous_block = chunk[index - 1]
        next_block = chunk[index] if index < len(chunk) else None
        _, boundary_ms = parse_timestamp_range(previous_block[1])
        duration = boundary_ms - start_ms
        score = abs(duration - target_ms)
        if not is_natural_boundary(previous_block, next_block):
            score += target_ms
        if best_score is None or score < best_score:
            best_score = score
            best_index = index

    return best_index


def build_chunks(
    blocks: list[tuple[str, str, list[str]]],
    target_minutes: float,
) -> list[list[tuple[str, str, list[str]]]]:
    if not blocks:
        return []

    chunks: list[list[tuple[str, str, list[str]]]] = []
    current: list[tuple[str, str, list[str]]] = []
    target_ms = int(target_minutes * 60 * 1000)
    chunk_start_ms: int | None = None

    for block in blocks:
        _, timestamp, _ = block
        start_ms, end_ms = parse_timestamp_range(timestamp)
        if chunk_start_ms is None:
            chunk_start_ms = start_ms

        current.append(block)
        if (end_ms - chunk_start_ms) <= target_ms:
            continue

        split_index = choose_split_index(current, target_ms=target_ms)
        chunks.append(current[:split_index])
        current = current[split_index:]
        if current:
            chunk_start_ms, _ = parse_timestamp_range(current[0][1])
        else:
            chunk_start_ms = None

    if current:
        chunks.append(current)

    return chunks


def split_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    chunk_dir = Path(args.output_dir) if args.output_dir else input_path.with_name(f"{input_path.stem}.chunks")
    chunk_dir.mkdir(parents=True, exist_ok=True)

    blocks = read_blocks(input_path)
    chunks = build_chunks(blocks, target_minutes=args.target_minutes)

    manifest = {
        "source": str(input_path),
        "chunk_dir": str(chunk_dir),
        "chunk_count": len(chunks),
        "total_blocks": len(blocks),
        "chunks": [],
    }

    for index, chunk in enumerate(chunks, start=1):
        source_name = f"{index:03d}.source.srt"
        translated_name = f"{index:03d}.translated.srt"
        source_path = chunk_dir / source_name

        source_path.write_text(render_blocks(chunk, keep_line_breaks=False), encoding="utf-8", newline="\n")

        start_cue = chunk[0][0]
        end_cue = chunk[-1][0]

        manifest["chunks"].append(
            {
                "index": index,
                "source_file": source_name,
                "translated_file": translated_name,
                "start_cue": start_cue,
                "end_cue": end_cue,
                "block_count": len(chunk),
            }
        )

    manifest_path = chunk_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print(f"[OK] Split {len(blocks)} blocks into {len(chunks)} chunks")
    print(f"[OK] Wrote {manifest_path}")
    return 0


def merge_command(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"[ERROR] Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunk_dir = manifest_path.parent
    merged_blocks: list[tuple[str, str, list[str]]] = []

    for chunk in manifest["chunks"]:
        source_path = chunk_dir / chunk["source_file"]
        translated_path = chunk_dir / chunk["translated_file"]
        if not source_path.exists():
            print(f"[ERROR] Missing source chunk: {source_path}", file=sys.stderr)
            return 1
        if not translated_path.exists():
            print(f"[ERROR] Missing translated chunk: {translated_path}", file=sys.stderr)
            return 1

        source_blocks = read_blocks(source_path)
        translated_blocks = read_blocks(translated_path)
        valid, error_message = validate_translated_chunk(source_blocks, translated_blocks, int(chunk["index"]))
        if not valid:
            print(f"[ERROR] {error_message}", file=sys.stderr)
            return 1

        merged_blocks.extend(translated_blocks)

    total_blocks = len(merged_blocks)
    expected_total = int(manifest["total_blocks"])
    if total_blocks != expected_total:
        print(
            f"[ERROR] Total block count mismatch: expected {expected_total}, got {total_blocks}",
            file=sys.stderr,
        )
        return 1

    output_path = Path(args.output) if args.output else Path(manifest["source"]).with_name(
        f"{Path(manifest['source']).stem}-CN{Path(manifest['source']).suffix}"
    )

    renumbered = []
    for index, (_, timestamp, lines) in enumerate(merged_blocks, start=1):
        renumbered.append((str(index), timestamp, lines))

    output_path.write_text(render_blocks(renumbered, keep_line_breaks=False), encoding="utf-8", newline="\n")

    print(f"[OK] Merged {total_blocks} translated blocks")
    print(f"[OK] Wrote {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split large subtitle files into stable translation chunks and merge translated chunks back.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_parser = subparsers.add_parser("split", help="Split a subtitle file into chunk files")
    split_parser.add_argument("input", help="Path to input subtitle file")
    split_parser.add_argument("output_dir", nargs="?", help="Optional output chunk directory")
    split_parser.add_argument("--target-minutes", type=float, default=20.0, help="Target runtime minutes per chunk")
    split_parser.set_defaults(func=split_command)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge translated chunk files into a final subtitle file after verifying identical cue numbers and timestamps",
    )
    merge_parser.add_argument("manifest", help="Path to the manifest.json produced by split")
    merge_parser.add_argument("output", nargs="?", help="Optional final output subtitle path")
    merge_parser.set_defaults(func=merge_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
