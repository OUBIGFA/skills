#!/usr/bin/env python3
"""Flag suspicious orphan-tail cue pairs for the model to review before translation.

An "orphan tail" is a short trailing cue B that completes a sentence started in the
previous cue A. Typical signature:

- A does NOT end with terminal punctuation (`.`, `!`, `?`, `。`, `！`, `？`).
- B is short in duration (default <= 2.0s).
- B has few tokens (default <= 4 words).
- B ends with terminal punctuation.
- The timing gap between A and B is small (default <= 500ms).

This script only REPORTS candidates. It never rewrites the subtitle file, does not
change cue numbers, and does not move text across cues. The language model remains
in charge of deciding whether to merge a candidate during preprocessing.

The JSON report is designed to be consumed by the model before the translation
pass so the Orphan Tail Merge workflow step in SKILL.md can be performed faithfully.
"""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

from preprocess_srt import TERMINAL_PUNCTUATION, format_timecode, parse_blocks, parse_timestamp_range


# Words that commonly introduce a trailing continuation rather than a new sentence.
# Keep this set principled (general English function words); do not encode specific
# example content words — the other signals already fire strongly on real tails.
CONTINUATION_LEAD_WORDS = {
    # coordinating conjunctions
    "and", "or", "but", "so", "yet", "nor", "for",
    # subordinating conjunctions
    "because", "since", "though", "although", "while",
    # prepositions and light particles
    "to", "in", "on", "at", "with", "of", "by", "from", "into", "onto",
    "up", "down", "out", "off", "back", "over", "under",
    "around", "away", "through", "across", "along",
    # relative pronouns / wh-continuations
    "which", "that", "who", "whom", "whose", "where", "when",
    # deictics / pronouns
    "it", "them", "one", "ones", "this", "these", "those",
}

# Orphan-lead fragments: a complete short cue that clearly needs the NEXT cue to make sense.
ORPHAN_LEAD_PATTERNS = (
    re.compile(r"^(?:maybe|okay|ok|well|so|now|and|but|or|also|plus)[.,!?…]*$", re.IGNORECASE),
    re.compile(r"^(?:i|we|you|they|it|he|she)\s+(?:will|can|could|should|would|might|may)[.,!?…]*$", re.IGNORECASE),
    re.compile(r"^(?:what|which|where|when|how)\s+(?:i|we|you|they)\s+(?:need|want|use|get|do)[.,!?…]*$", re.IGNORECASE),
    re.compile(r"^(?:for|to|in|at|with)\s+\w+[.,!?…]*$", re.IGNORECASE),
)


def block_text(block: tuple[str, str, list[str]]) -> str:
    _, _, lines = block
    return " ".join(line.strip() for line in lines if line.strip()).strip()


def duration_ms(block: tuple[str, str, list[str]]) -> int:
    start, end = parse_timestamp_range(block[1])
    return max(0, end - start)


def gap_ms(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]],
) -> int:
    _, previous_end = parse_timestamp_range(previous[1])
    current_start, _ = parse_timestamp_range(current[1])
    return max(0, current_start - previous_end)


def word_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"[A-Za-z一-鿿][\w'’-]*", text))


def ends_with_terminal(text: str) -> bool:
    stripped = text.rstrip().rstrip("\"'”’)]}")
    return bool(stripped) and stripped[-1] in TERMINAL_PUNCTUATION


def leading_word(text: str) -> str:
    match = re.match(r"[A-Za-z'’-]+", text.strip())
    return match.group(0).lower() if match else ""


def merge_timestamp(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]],
) -> str:
    start, _ = parse_timestamp_range(previous[1])
    _, end = parse_timestamp_range(current[1])
    return f"{format_timecode(start)} --> {format_timecode(end)}"


def classify_tail(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]],
    *,
    max_tail_duration_ms: int,
    max_tail_words: int,
    max_gap_ms: int,
) -> tuple[bool, list[str]]:
    previous_text = block_text(previous)
    current_text = block_text(current)

    if not previous_text or not current_text:
        return False, []

    reasons: list[str] = []

    tail_duration = duration_ms(current)
    tail_words = word_count(current_text)
    pair_gap = gap_ms(previous, current)
    previous_complete = ends_with_terminal(previous_text)
    current_complete = ends_with_terminal(current_text)

    if previous_complete:
        return False, []

    # Signal 1: duration
    if tail_duration <= max_tail_duration_ms:
        reasons.append(f"short_tail_duration<={max_tail_duration_ms}ms({tail_duration}ms)")

    # Signal 2: word count
    if tail_words <= max_tail_words:
        reasons.append(f"short_word_count<={max_tail_words}words({tail_words}w)")

    # Signal 3: tail finishes a sentence
    if current_complete:
        reasons.append("tail_ends_sentence")

    # Signal 4: contiguous timing
    if pair_gap <= max_gap_ms:
        reasons.append(f"contiguous_timing<={max_gap_ms}ms({pair_gap}ms)")

    # Signal 5: tail starts with a continuation word
    lead = leading_word(current_text)
    if lead in CONTINUATION_LEAD_WORDS:
        reasons.append(f"continuation_lead('{lead}')")

    # Signal 6: tail starts lowercase (common ASR residue on continuation tails)
    first_char = current_text.lstrip()[:1]
    if first_char and first_char.islower():
        reasons.append("tail_starts_lowercase")

    # Decision: need multiple confirming signals to flag
    strong_enough = (
        current_complete
        and tail_duration <= max_tail_duration_ms
        and tail_words <= max_tail_words
        and pair_gap <= max_gap_ms
    )
    return strong_enough, reasons


def classify_orphan_lead(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]] | None,
) -> tuple[bool, list[str]]:
    previous_text = block_text(previous)
    if not previous_text:
        return False, []
    if not current:
        return False, []
    if ends_with_terminal(previous_text) and word_count(previous_text) >= 3:
        return False, []

    reasons: list[str] = []
    for pattern in ORPHAN_LEAD_PATTERNS:
        if pattern.match(previous_text):
            reasons.append(f"orphan_lead_pattern('{pattern.pattern}')")
            break
    if not reasons:
        return False, []

    current_text = block_text(current)
    if current_text and leading_word(current_text) not in CONTINUATION_LEAD_WORDS:
        # Previous looks like an orphan lead AND the next cue clearly continues it.
        reasons.append("next_cue_continues")
    return True, reasons


def detect_candidates(
    blocks: list[tuple[str, str, list[str]]],
    *,
    max_tail_duration_ms: int,
    max_tail_words: int,
    max_gap_ms: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []

    for index in range(1, len(blocks)):
        previous = blocks[index - 1]
        current = blocks[index]

        is_tail, tail_reasons = classify_tail(
            previous,
            current,
            max_tail_duration_ms=max_tail_duration_ms,
            max_tail_words=max_tail_words,
            max_gap_ms=max_gap_ms,
        )
        if is_tail:
            merged_text = f"{block_text(previous)} {block_text(current)}".strip()
            candidates.append(
                {
                    "kind": "orphan_tail",
                    "merge_cues": [previous[0], current[0]],
                    "cue_a": {
                        "number": previous[0],
                        "timestamp": previous[1],
                        "text": block_text(previous),
                    },
                    "cue_b": {
                        "number": current[0],
                        "timestamp": current[1],
                        "text": block_text(current),
                    },
                    "reasons": tail_reasons,
                    "preview": {
                        "timestamp": merge_timestamp(previous, current),
                        "text": merged_text,
                        "note": "Preview only. The model decides whether to merge. Renumber sequentially after any merge.",
                    },
                }
            )
            continue

        # Also check if previous is an orphan-lead fragment feeding into current.
        is_lead, lead_reasons = classify_orphan_lead(previous, current)
        if is_lead:
            merged_text = f"{block_text(previous)} {block_text(current)}".strip()
            candidates.append(
                {
                    "kind": "orphan_lead",
                    "merge_cues": [previous[0], current[0]],
                    "cue_a": {
                        "number": previous[0],
                        "timestamp": previous[1],
                        "text": block_text(previous),
                    },
                    "cue_b": {
                        "number": current[0],
                        "timestamp": current[1],
                        "text": block_text(current),
                    },
                    "reasons": lead_reasons,
                    "preview": {
                        "timestamp": merge_timestamp(previous, current),
                        "text": merged_text,
                        "note": "Preview only. The model decides whether to merge. Renumber sequentially after any merge.",
                    },
                }
            )

    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Flag suspicious orphan-tail (and orphan-lead) cue pairs for the model "
            "to review before translation. Report-only: never rewrites the subtitle."
        ),
    )
    parser.add_argument("input", help="Path to the input subtitle file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Optional report JSON path. Defaults to a sibling .orphan-tails.json file.",
    )
    parser.add_argument(
        "--max-tail-duration-ms",
        type=int,
        default=2000,
        help="Maximum on-screen duration for a cue to count as a short tail (default 2000ms)",
    )
    parser.add_argument(
        "--max-tail-words",
        type=int,
        default=4,
        help="Maximum word count for a cue to count as a short tail (default 4)",
    )
    parser.add_argument(
        "--max-gap-ms",
        type=int,
        default=500,
        help="Maximum silence gap between A and B to count as contiguous (default 500ms)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout summary lines (the JSON report is still written).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else input_path.with_name(
        f"{input_path.stem}.orphan-tails.json"
    )

    content = input_path.read_text(encoding="utf-8-sig")
    try:
        blocks = parse_blocks(content)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    candidates = detect_candidates(
        blocks,
        max_tail_duration_ms=args.max_tail_duration_ms,
        max_tail_words=args.max_tail_words,
        max_gap_ms=args.max_gap_ms,
    )

    payload = {
        "source": str(input_path),
        "total_blocks": len(blocks),
        "candidate_count": len(candidates),
        "thresholds": {
            "max_tail_duration_ms": args.max_tail_duration_ms,
            "max_tail_words": args.max_tail_words,
            "max_gap_ms": args.max_gap_ms,
        },
        "policy": (
            "Report-only. The model decides whether to merge each candidate during "
            "preprocessing. After any merge, combine timestamps (start of A, end of B), "
            "join the text, and renumber the whole subtitle sequentially from 1."
        ),
        "candidates": candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    if not args.quiet:
        print(f"[OK] Scanned {len(blocks)} blocks")
        print(f"[OK] Flagged {len(candidates)} orphan-tail / orphan-lead candidates")
        print(f"[OK] Wrote {output_path}")
        if candidates:
            print("[HINT] Review the report and perform the merges in the preprocessing pass; the script did not modify the subtitle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
