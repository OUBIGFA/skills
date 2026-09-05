#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble UTF-8 subtitle parts without duplicating format headers.

Usage:
    python assemble_subtitle.py output.srt part1.srt part2.srt
"""

import argparse
import sys
from pathlib import Path


def read_part(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("%s must be UTF-8" % path) from exc


def split_vtt(text):
    chunks = text.strip().split("\n\n")
    if chunks and chunks[0].lstrip().startswith("WEBVTT"):
        return chunks[0], chunks[1:]
    return "", chunks


def extract_ass_events(text):
    lines = text.splitlines()
    event_start = next((i for i, line in enumerate(lines)
                        if line.strip().lower() == "[events]"), None)
    if event_start is not None:
        lines = lines[event_start + 1:]
    return [line for line in lines
            if line.strip() and not line.strip().lower().startswith("format:")
            and (line.strip().lower().startswith(("dialogue:", "comment:", "picture:", "sound:", "movie:")))]


def assemble(output_path, part_paths):
    fmt = Path(output_path).suffix.lower()
    if fmt not in (".srt", ".vtt", ".ass", ".ssa"):
        raise ValueError("output extension must be .srt, .vtt, .ass, or .ssa")
    parts = [read_part(path) for path in part_paths]
    if not parts:
        raise ValueError("at least one part is required")

    if fmt == ".srt":
        result = "\n\n".join(part.strip() for part in parts if part.strip()) + "\n\n"
    elif fmt == ".vtt":
        headers, bodies = zip(*(split_vtt(part) for part in parts))
        header = next((item for item in headers if item), "WEBVTT")
        chunks = [chunk for body in bodies for chunk in body if chunk.strip()]
        result = header + ("\n\n" + "\n\n".join(chunks) if chunks else "") + "\n"
    else:
        first = parts[0].strip()
        events = extract_ass_events("\n".join(parts[1:]))
        result = first + ("\n" + "\n".join(events) if events else "") + "\n"

    Path(output_path).write_text(result, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="assembled UTF-8 output path")
    parser.add_argument("parts", nargs="+", help="ordered UTF-8 subtitle parts")
    args = parser.parse_args()
    try:
        assemble(args.output, args.parts)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
