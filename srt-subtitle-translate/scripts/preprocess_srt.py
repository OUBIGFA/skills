#!/usr/bin/env python3
"""Normalize subtitle text in SRT-like timed blocks without touching cue boundaries.

This script is deliberately restricted to whitespace and formatting normalization:
- trims surrounding whitespace,
- collapses repeated internal whitespace,
- drops empty text lines and fully empty cues,
- joins wrapped text into a single line per cue by default,
- renumbers cues sequentially starting at 1.

Cue boundaries, timestamps, sentence segmentation, and readability/length
decisions are intentionally NOT automated here. All sentence-boundary repair
(merging or splitting adjacent cues, redistributing timestamps, shortening
overlong cues, etc.) must be performed by the language model based on semantic
understanding. See SKILL.md for the policy rationale.
"""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import re


TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s-->\s\d{2}:\d{2}:\d{2},\d{3}"
    r"(?:\s+.*)?$"
)

# Exposed for chunk-boundary heuristics in `chunk_srt.py`.
# This module does not use it for any automatic cue resegmentation — chunk
# boundary selection happens later on the chunk-planning side, not here.
TERMINAL_PUNCTUATION = ".!?。！？"


def parse_timecode(value: str) -> int:
    hours = int(value[0:2])
    minutes = int(value[3:5])
    seconds = int(value[6:8])
    millis = int(value[9:12])
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def format_timecode(total_ms: int) -> str:
    total_ms = max(0, total_ms)
    millis = total_ms % 1000
    total_seconds = total_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_timestamp_range(timestamp: str) -> tuple[int, int]:
    start, end = [part.strip() for part in timestamp.split("-->")]
    return parse_timecode(start), parse_timecode(end)


def make_timestamp(start_ms: int, end_ms: int) -> str:
    return f"{format_timecode(start_ms)} --> {format_timecode(end_ms)}"


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_source_text(text: str) -> str:
    text = collapse_spaces(text)
    text = re.sub(r"\.\s*\.\s*\.(?:\s*\.)*", "...", text)
    text = re.sub(r"(?<=\w)\.\s*\.(?=\s*\w)", ".", text)
    text = re.sub(r"(?<=\w)\.\.(?=\s*\w)", ".", text)
    text = re.sub(r"([.!?。！？])(?=(?:[\"'”’\)\]]*)[A-Z\u4e00-\u9fff])", r"\1 ", text)
    text = re.sub(
        r"\b(We|I|You|They)\s+can\s+(we'll|i'll|you'll|they'll)\b",
        lambda m: m.group(2)[0].upper() + m.group(2)[1:],
        text,
        flags=re.IGNORECASE,
    )
    return collapse_spaces(text)


def parse_blocks(content: str) -> list[tuple[str, str, list[str]]]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = [block for block in re.split(r"\n{2,}", normalized.strip()) if block.strip()]
    blocks: list[tuple[str, str, list[str]]] = []

    for index, block in enumerate(raw_blocks, start=1):
        lines = [line.rstrip() for line in block.split("\n")]
        if len(lines) < 2:
            raise ValueError(f"Block {index} is incomplete")

        cue = lines[0].strip()
        timestamp = lines[1].strip()
        text_lines = lines[2:]

        if not cue.isdigit():
            raise ValueError(f"Block {index} has invalid cue number: {cue!r}")
        if not TIMESTAMP_RE.match(timestamp):
            raise ValueError(f"Block {index} has invalid timestamp: {timestamp!r}")

        blocks.append((cue, timestamp, text_lines))

    return blocks


def drop_empty_blocks(
    blocks: list[tuple[str, str, list[str]]],
) -> list[tuple[str, str, list[str]]]:
    return [
        (cue, timestamp, text_lines)
        for cue, timestamp, text_lines in blocks
        if any(collapse_spaces(line) for line in text_lines)
    ]


def normalize_text_lines(lines: list[str], keep_line_breaks: bool) -> list[str]:
    cleaned = [normalize_source_text(line) for line in lines if collapse_spaces(line)]
    if not cleaned:
        return []
    if keep_line_breaks:
        return cleaned
    return [collapse_spaces(" ".join(cleaned))]


def renumber_blocks(blocks: list[tuple[str, str, list[str]]]) -> list[tuple[str, str, list[str]]]:
    renumbered: list[tuple[str, str, list[str]]] = []
    for index, (_, timestamp, text_lines) in enumerate(blocks, start=1):
        renumbered.append((str(index), timestamp, text_lines))
    return renumbered


def render_blocks(blocks: list[tuple[str, str, list[str]]], keep_line_breaks: bool) -> str:
    rendered: list[str] = []
    for cue, timestamp, text_lines in blocks:
        if keep_line_breaks:
            normalized_lines = normalize_text_lines(text_lines, True)
        else:
            normalized_lines = [collapse_spaces(line) for line in text_lines if collapse_spaces(line)]
        block_lines = [cue, timestamp, *normalized_lines]
        rendered.append("\n".join(block_lines))
    return "\n\n".join(rendered) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize subtitle text in SRT-like timed blocks. Preserves cue "
            "boundaries and timestamps; does not perform any automatic sentence "
            "resegmentation. Sentence-boundary decisions must be made by the "
            "language model."
        ),
    )
    parser.add_argument("input", help="Path to input subtitle file, such as .srt or .txt")
    parser.add_argument(
        "output",
        nargs="?",
        help=(
            "Optional output subtitle path. Defaults to a sibling .preprocessed file. "
            "Do NOT use the final -CN name here; -CN is reserved for the final translated output."
        ),
    )
    parser.add_argument(
        "--keep-line-breaks",
        action="store_true",
        help="Preserve per-cue line breaks instead of joining text into one line.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}.preprocessed{input_path.suffix}")

    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    content = input_path.read_text(encoding="utf-8-sig")

    try:
        blocks = parse_blocks(content)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    blocks = drop_empty_blocks(blocks)
    blocks = renumber_blocks(blocks)

    output = render_blocks(blocks, args.keep_line_breaks)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8", newline="\n")

    print(f"[OK] Normalized {len(blocks)} subtitle blocks")
    print(f"[OK] Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
