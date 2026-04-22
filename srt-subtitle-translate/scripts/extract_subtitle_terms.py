#!/usr/bin/env python3
"""Extract recurring candidate names and terms from SRT-like subtitle files for translation consistency."""

from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import re

from preprocess_srt import parse_blocks


ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:\d+[A-Z]*)?\b")
CAPITALIZED_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?)(?:\s+(?:[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?|to|of|and|for|in)){0,4}\b")
CAMEL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b")
VERSIONED_RE = re.compile(r"\b(?:[A-Z][A-Za-z]+|\d+[A-Za-z]+|[A-Za-z]+\d+)\b")

STOP_TERMS = {
    "I", "I'll", "I've", "I'd", "It", "It's", "We", "We're", "You", "You're",
    "And", "But", "So", "Then", "Now", "Today", "Okay", "OK", "Hello",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_blocks(path: Path) -> list[tuple[str, str, list[str]]]:
    content = path.read_text(encoding="utf-8-sig")
    return parse_blocks(content)


def collect_candidates(blocks: list[tuple[str, str, list[str]]]) -> dict[str, dict[str, object]]:
    hits: Counter[str] = Counter()
    first_cue: dict[str, str] = {}
    examples: defaultdict[str, list[str]] = defaultdict(list)

    patterns = (ACRONYM_RE, CAMEL_RE, CAPITALIZED_RE, VERSIONED_RE)

    for cue, _, lines in blocks:
        text = normalize_space(" ".join(lines))
        if not text:
            continue

        found: set[str] = set()
        for pattern in patterns:
            for match in pattern.finditer(text):
                term = normalize_space(match.group(0).strip(".,:;!?()[]{}\"'"))
                if not term or term in STOP_TERMS or len(term) <= 1:
                    continue
                if term.lower() in {"the", "a", "an"}:
                    continue
                found.add(term)

        for term in sorted(found):
            hits[term] += 1
            first_cue.setdefault(term, cue)
            if len(examples[term]) < 3:
                examples[term].append(text)

    result: dict[str, dict[str, object]] = {}
    for term, count in hits.most_common():
        if count < 2 and " " not in term and not any(ch.isdigit() for ch in term):
            continue
        result[term] = {
            "count": count,
            "first_cue": first_cue[term],
            "suggested_translation": "",
            "notes": "",
            "examples": examples[term],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract recurring candidate names and terms from subtitle files for translation consistency.",
    )
    parser.add_argument("input", help="Path to the input subtitle file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Optional output JSON path. Defaults to a sibling .terms.json file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}.terms.json")
    blocks = read_blocks(input_path)
    candidates = collect_candidates(blocks)

    payload = {
        "source": str(input_path),
        "term_count": len(candidates),
        "terms": candidates,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print(f"[OK] Extracted {len(candidates)} candidate terms")
    print(f"[OK] Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
