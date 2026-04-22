#!/usr/bin/env python3
"""Flag clause-boundary rebalance candidates for the model to review before translation.

A "clause boundary split" is a pair of adjacent cues (A, B) where cue A ends with a
DANGLING tail — a trailing conjunction, bare preposition, bare auxiliary or modal,
bare subject pronoun, subject-plus-modal pair, or bare determiner — and cue B
continues and completes the clause. The correct repair is to SHIFT the dangling
tail forward into cue B at the natural semantic hinge and REDISTRIBUTE timestamps
proportionally across the combined span. Both cues stay — only the cut point and
timestamps change.

This is distinct from the orphan-tail pattern handled by `detect_orphan_tails.py`
(which merges a short trailing fragment back into the previous cue and drops a
cue). Candidates where cue B is itself a short fragment are intentionally filtered
out here so the two reports are disjoint; those belong to the orphan-tail sweep.

This script only REPORTS candidates. It never rewrites the subtitle file, does
not change cue numbers, and does not retime cues. The language model remains in
charge of deciding whether and where to rebalance each candidate during
preprocessing.

The JSON report is designed to be consumed by the model before the translation
pass so the Clause Boundary Rebalance workflow step in SKILL.md can be performed
faithfully.
"""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

from preprocess_srt import (
    TERMINAL_PUNCTUATION,
    format_timecode,
    parse_blocks,
    parse_timestamp_range,
)


# ---------------------------------------------------------------------------
# Dangling-tail vocabulary
# ---------------------------------------------------------------------------
# These sets describe the GRAMMATICAL role of the LAST 1 or 2 tokens of cue A.
# If the tail matches a known dangling pattern, the pair becomes a candidate
# for clause-boundary rebalance.
#
# The vocabulary is intentionally general. It does not encode domain-specific
# content words; the semantic decision of whether to actually shift the tail
# is left to the language model reviewing the report.

SUBORDINATING_CONJUNCTIONS = {
    "because", "since", "if", "when", "where", "while", "as", "after", "before",
    "until", "although", "though", "unless", "whereas",
}

COORDINATING_CONJUNCTIONS = {
    "and", "but", "or", "nor", "so", "yet", "for",
}

RELATIVE_PRONOUNS = {
    "which", "that", "who", "whom", "whose",
}

COMMON_PREPOSITIONS = {
    "in", "on", "at", "to", "with", "from", "of", "by", "for", "about",
    "into", "onto", "upon", "through", "across", "over", "under",
    "between", "among", "against", "without", "within", "toward", "towards",
}

AUXILIARIES_MODALS = {
    "will", "can", "could", "should", "would", "might", "may", "must", "shall",
    "do", "does", "did", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had",
}

SUBJECT_PRONOUNS = {
    "i", "we", "you", "they", "he", "she", "it",
}

DETERMINERS = {
    "the", "a", "an", "my", "our", "your", "their", "his", "her", "its",
    "this", "that", "these", "those", "some", "any", "every", "each",
}

PATTERN_LABELS = {
    "subordinating_conjunction",
    "coordinating_conjunction",
    "relative_pronoun",
    "preposition",
    "auxiliary_modal",
    "subject_pronoun",
    "determiner",
    "subject_plus_modal",
    "conjunction_plus_subject",
    "preposition_plus_determiner",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text)


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
    return len(tokenize(text))


def ends_with_terminal(text: str) -> bool:
    stripped = text.rstrip().rstrip("\"'”’)]}")
    return bool(stripped) and stripped[-1] in TERMINAL_PUNCTUATION


def find_dangling_tail(text: str) -> tuple[str, str] | None:
    """Return (dangling_tail, pattern_label) if cue A ends with a dangling tail.

    Checks the last 2 tokens first (more specific combined patterns), then falls
    back to the last single token. Returns None when no dangling tail is found.
    """
    tokens = tokenize(text)
    if not tokens:
        return None

    last1 = tokens[-1].lower()
    last2 = tokens[-2].lower() if len(tokens) >= 2 else None

    # Two-word patterns first so they take priority over single-word matches.
    if last2 is not None:
        # "we can", "I will", "you should"
        if last2 in SUBJECT_PRONOUNS and last1 in AUXILIARIES_MODALS:
            return (f"{tokens[-2]} {tokens[-1]}", "subject_plus_modal")
        # "because we", "but I", "so they", "which they"
        if (
            last2 in (SUBORDINATING_CONJUNCTIONS | COORDINATING_CONJUNCTIONS | RELATIVE_PRONOUNS)
            and last1 in SUBJECT_PRONOUNS
        ):
            return (f"{tokens[-2]} {tokens[-1]}", "conjunction_plus_subject")
        # "to the", "in a", "on our"
        if last2 in COMMON_PREPOSITIONS and last1 in DETERMINERS:
            return (f"{tokens[-2]} {tokens[-1]}", "preposition_plus_determiner")

    # Single-word patterns. Order matters only for the label; membership is disjoint.
    if last1 in SUBORDINATING_CONJUNCTIONS:
        return (tokens[-1], "subordinating_conjunction")
    if last1 in COORDINATING_CONJUNCTIONS:
        return (tokens[-1], "coordinating_conjunction")
    if last1 in RELATIVE_PRONOUNS:
        return (tokens[-1], "relative_pronoun")
    if last1 in COMMON_PREPOSITIONS:
        return (tokens[-1], "preposition")
    if last1 in AUXILIARIES_MODALS:
        return (tokens[-1], "auxiliary_modal")
    if last1 in DETERMINERS:
        return (tokens[-1], "determiner")
    if last1 in SUBJECT_PRONOUNS:
        return (tokens[-1], "subject_pronoun")

    return None


def compute_rebalance(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]],
    dangling_tail: str,
) -> dict[str, object] | None:
    """Propose a rebalanced (text_a, text_b, timestamps) for the model to review.

    Uses character-length proportion across the combined span to compute the new
    split timestamp. Rounds to the nearest 10 ms for cleaner timestamps.
    """
    prev_text = block_text(previous)
    curr_text = block_text(current)
    prev_start, _ = parse_timestamp_range(previous[1])
    _, curr_end = parse_timestamp_range(current[1])

    # Case-insensitive match against the actual tail at the end of prev_text.
    tail_tokens = dangling_tail.split()
    # Reconstruct boundary: find the position in prev_text where the dangling
    # tail starts. We search from the right to be safe against earlier matches.
    prev_tokens_with_spans: list[tuple[str, int, int]] = []
    for match in _WORD_RE.finditer(prev_text):
        prev_tokens_with_spans.append((match.group(0), match.start(), match.end()))

    if len(prev_tokens_with_spans) < len(tail_tokens):
        return None

    tail_start_token = prev_tokens_with_spans[-len(tail_tokens)]
    tail_start_char = tail_start_token[1]

    new_prev_text = prev_text[:tail_start_char].rstrip(" ,;:—–-")
    actual_tail_text = prev_text[tail_start_char:].strip()
    new_curr_text = f"{actual_tail_text} {curr_text}".strip()

    if not new_prev_text or not new_curr_text:
        return None

    # Proportional split by character length across the combined span.
    total_len = len(new_prev_text) + len(new_curr_text)
    if total_len <= 0:
        return None
    fraction = len(new_prev_text) / total_len

    combined_span = max(0, curr_end - prev_start)
    new_split_ms = prev_start + int(round(combined_span * fraction))
    # Snap to the nearest 10 ms for a cleaner timestamp.
    new_split_ms = int(round(new_split_ms / 10.0)) * 10
    # Clamp within the combined span.
    new_split_ms = max(prev_start + 1, min(curr_end - 1, new_split_ms))

    return {
        "new_prev_text": new_prev_text,
        "new_curr_text": new_curr_text,
        "new_prev_timestamp": f"{format_timecode(prev_start)} --> {format_timecode(new_split_ms)}",
        "new_curr_timestamp": f"{format_timecode(new_split_ms)} --> {format_timecode(curr_end)}",
        "combined_span": f"{format_timecode(prev_start)} --> {format_timecode(curr_end)}",
        "hinge_word": actual_tail_text.split(" ", 1)[0],
    }


# ---------------------------------------------------------------------------
# Candidate detection
# ---------------------------------------------------------------------------

def classify_clause_rebalance(
    previous: tuple[str, str, list[str]],
    current: tuple[str, str, list[str]],
    *,
    max_gap_ms: int,
    min_tail_words_for_b: int,
    min_prev_words_after_cut: int,
) -> tuple[bool, list[str], dict[str, object] | None]:
    """Decide whether (previous, current) is a clause-rebalance candidate."""
    prev_text = block_text(previous)
    curr_text = block_text(current)

    if not prev_text or not curr_text:
        return False, [], None

    # Skip when A already terminates a sentence — there's no dangling tail.
    if ends_with_terminal(prev_text):
        return False, [], None

    # Skip when B is itself a short trailing fragment — that belongs to the
    # Orphan Tail Merge sweep, not clause rebalance.
    if word_count(curr_text) < min_tail_words_for_b:
        return False, [], None

    # Skip large gaps that likely represent a scene / speaker change.
    pair_gap = gap_ms(previous, current)
    if pair_gap > max_gap_ms:
        return False, [], None

    dangling = find_dangling_tail(prev_text)
    if dangling is None:
        return False, [], None

    dangling_tail, pattern_label = dangling

    reasons: list[str] = [f"pattern('{pattern_label}')", f"tail('{dangling_tail}')"]
    reasons.append(f"contiguous_timing<={max_gap_ms}ms({pair_gap}ms)")

    preview = compute_rebalance(previous, current, dangling_tail)
    if preview is None:
        return False, [], None

    # Guard against producing a sliver on the A side after the cut.
    new_prev_words = word_count(preview["new_prev_text"])  # type: ignore[index]
    if new_prev_words < min_prev_words_after_cut:
        return False, [], None

    reasons.append(f"new_prev_words>={min_prev_words_after_cut}({new_prev_words}w)")
    return True, reasons, preview


def detect_candidates(
    blocks: list[tuple[str, str, list[str]]],
    *,
    max_gap_ms: int = 500,
    min_tail_words_for_b: int = 5,
    min_prev_words_after_cut: int = 3,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []

    for index in range(1, len(blocks)):
        previous = blocks[index - 1]
        current = blocks[index]
        is_candidate, reasons, preview = classify_clause_rebalance(
            previous,
            current,
            max_gap_ms=max_gap_ms,
            min_tail_words_for_b=min_tail_words_for_b,
            min_prev_words_after_cut=min_prev_words_after_cut,
        )
        if not is_candidate or preview is None:
            continue

        candidates.append(
            {
                "kind": "clause_rebalance",
                "rebalance_cues": [previous[0], current[0]],
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
                "dangling_tail": preview["hinge_word"],  # type: ignore[index]
                "reasons": reasons,
                "preview": {
                    "combined_span": preview["combined_span"],
                    "new_cue_a": {
                        "timestamp": preview["new_prev_timestamp"],
                        "text": preview["new_prev_text"],
                    },
                    "new_cue_b": {
                        "timestamp": preview["new_curr_timestamp"],
                        "text": preview["new_curr_text"],
                    },
                    "note": (
                        "Preview only. Proportional split by character length, "
                        "rounded to the nearest 10 ms. The model decides the "
                        "final hinge based on semantics and may pick a slightly "
                        "different split point. Renumber the whole subtitle "
                        "sequentially after any rebalance."
                    ),
                },
            }
        )

    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Flag clause-boundary rebalance candidates for the model to review "
            "before translation. Report-only: never rewrites the subtitle."
        ),
    )
    parser.add_argument("input", help="Path to the input subtitle file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Optional report JSON path. Defaults to a sibling .clause-rebalance.json file.",
    )
    parser.add_argument(
        "--max-gap-ms",
        type=int,
        default=500,
        help="Maximum silence gap between A and B to count as contiguous (default 500ms)",
    )
    parser.add_argument(
        "--min-tail-words-for-b",
        type=int,
        default=5,
        help=(
            "Minimum word count of cue B to count as a clause-rebalance "
            "candidate. Shorter B cues belong to the orphan-tail sweep. "
            "(default 5)"
        ),
    )
    parser.add_argument(
        "--min-prev-words-after-cut",
        type=int,
        default=3,
        help=(
            "Minimum word count that must remain on cue A after the proposed "
            "rebalance cut, to avoid producing a sliver cue. (default 3)"
        ),
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
        f"{input_path.stem}.clause-rebalance.json"
    )

    content = input_path.read_text(encoding="utf-8-sig")
    try:
        blocks = parse_blocks(content)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    candidates = detect_candidates(
        blocks,
        max_gap_ms=args.max_gap_ms,
        min_tail_words_for_b=args.min_tail_words_for_b,
        min_prev_words_after_cut=args.min_prev_words_after_cut,
    )

    payload = {
        "source": str(input_path),
        "total_blocks": len(blocks),
        "candidate_count": len(candidates),
        "thresholds": {
            "max_gap_ms": args.max_gap_ms,
            "min_tail_words_for_b": args.min_tail_words_for_b,
            "min_prev_words_after_cut": args.min_prev_words_after_cut,
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    if not args.quiet:
        print(f"[OK] Scanned {len(blocks)} blocks")
        print(f"[OK] Flagged {len(candidates)} clause-rebalance candidates")
        print(f"[OK] Wrote {output_path}")
        if candidates:
            print("[HINT] Review the report and perform the rebalance in the preprocessing pass; the script did not modify the subtitle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
