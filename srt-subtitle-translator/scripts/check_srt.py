#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_srt.py — structural and readability validator for translated SRT files.

Two ways to use it:

    python check_srt.py out.zh.srt                  # check one file
    python check_srt.py out.zh.srt --source in.srt  # also diff against the source

Checks performed on the output file:
  - parseable SRT, indices sequential from 1, no empty text block
  - start < end, no overlap with the following block
  - duration below/above comfort thresholds, characters-per-second load
  - one line per block (wrapping is not allowed; condense instead)
  - sentence-final punctuation at end of a text line
  - missing space between CJK and Latin/digits (reported, not fatal)

Extra checks when --source is given:
  - every output start/end time already exists in the source timeline
  - the union of output intervals equals the union of source intervals
    (nothing dropped, nothing invented, no re-timing)
  - block-count delta and the merge factor of each output block

Exit code 0 = no errors (warnings may still be printed), 1 = errors found.
"""

import argparse
import json
import re
import sys
import unicodedata

# Subtitle text is CJK; never let a legacy console codepage mangle the report.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)

# Timing defaults follow the Netflix Timed Text Style Guide (9 chars/second for
# adult Simplified Chinese programming, minimum 20 frames, maximum 7 s per event).
# There is deliberately no per-line character limit: reading load is a function of
# time, not of line width, and a character budget only ever produces unnatural
# breaks. Blocks are one line each; when the text is too dense for its window the
# fix is to condense, never to wrap.
# Override from the command line when a project has its own spec.
DEFAULTS = {
    "min_duration": 0.833,    # seconds; 20 frames @24fps — shorter blocks flash by unread
    "max_duration": 7.0,      # seconds; longer blocks feel stuck on screen
    "max_cps": 9.0,           # full-width chars per second (Netflix zh-Hans, adult)
    "max_lines": 1,           # bilingual and multi-speaker output may raise this
}

SENT_FINAL = "。．.!！?？;；:：、,，"
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿぀-ヿ]")
LATIN_RE = re.compile(r"[A-Za-z0-9]")
PUNCT_CATEGORIES = {"P", "S", "Z", "C"}


def parse_srt(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit("cannot decode %s as utf-8/gb18030/utf-16" % path)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks, errors = [], []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in chunk.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        idx_line, time_line_pos = None, 0
        if TIME_RE.match(lines[0]):
            time_line_pos = 0
        elif len(lines) > 1 and TIME_RE.match(lines[1]):
            idx_line, time_line_pos = lines[0].strip(), 1
        else:
            errors.append("unparseable block near: %s" % lines[0][:60])
            continue
        m = TIME_RE.match(lines[time_line_pos])
        start = to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
        end = to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
        blocks.append(
            {
                "index": int(idx_line) if idx_line and idx_line.isdigit() else None,
                "start": start,
                "end": end,
                "time_line": lines[time_line_pos].strip(),
                "lines": lines[time_line_pos + 1 :],
            }
        )
    return blocks, errors


def to_seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def fmt(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def display_width(text):
    """Cost in full-width units, ignoring punctuation and spaces.

    A Chinese character costs 1, a Latin letter or digit costs 0.5. Punctuation
    is skipped because it carries almost no reading load.
    """
    total = 0.0
    for ch in text:
        if unicodedata.category(ch)[0] in PUNCT_CATEGORIES:
            continue
        total += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
    return total


def merge_intervals(blocks):
    spans = sorted((b["start"], b["end"]) for b in blocks)
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(x) for x in merged]


def check(out_path, src_path, cfg):
    errors, warnings, notes = [], [], []
    blocks, parse_errors = parse_srt(out_path)
    errors.extend(parse_errors)
    if not blocks:
        errors.append("no subtitle blocks found in %s" % out_path)
        return blocks, errors, warnings, notes

    for i, b in enumerate(blocks):
        pos = "#%d %s" % (i + 1, b["time_line"])
        if b["index"] is not None and b["index"] != i + 1:
            errors.append("%s: index is %s, expected %d" % (pos, b["index"], i + 1))
        text = " ".join(b["lines"]).strip()
        if not text:
            errors.append("%s: empty subtitle text" % pos)
            continue
        if b["end"] <= b["start"]:
            errors.append("%s: end time is not after start time" % pos)
        if i + 1 < len(blocks) and blocks[i + 1]["start"] < b["end"] - 1e-6:
            errors.append("%s: overlaps the next block" % pos)

        dur = max(b["end"] - b["start"], 1e-6)
        width = display_width(text)
        cps = width / dur
        if dur < cfg["min_duration"]:
            warnings.append("%s: only %.2fs on screen — %s" % (pos, dur, text[:30]))
        if dur > cfg["max_duration"]:
            warnings.append("%s: %.1fs on screen, longer than %.1fs" % (pos, dur, cfg["max_duration"]))
        if cps > cfg["max_cps"]:
            warnings.append(
                "%s: %.1f chars/s (limit %.1f), %.0f chars in %.2fs — %s"
                % (pos, cps, cfg["max_cps"], width, dur, text[:30])
            )
        if len(b["lines"]) > cfg["max_lines"]:
            warnings.append(
                "%s: %d lines — a block is one line; condense the text instead of wrapping it"
                % (pos, len(b["lines"]))
            )
        for ln in b["lines"]:
            if ln.rstrip() and ln.rstrip()[-1] in SENT_FINAL:
                warnings.append("%s: line ends with '%s'" % (pos, ln.rstrip()[-1]))
        for m in re.finditer(r"(?:%s)(?:%s)|(?:%s)(?:%s)"
                             % (CJK_RE.pattern, LATIN_RE.pattern,
                                LATIN_RE.pattern, CJK_RE.pattern), text):
            notes.append("%s: missing space at '%s'" % (pos, m.group(0)))

    if src_path:
        src, src_parse_errors = parse_srt(src_path)
        errors.extend("source: " + e for e in src_parse_errors)
        src_starts = {round(b["start"], 3) for b in src}
        src_ends = {round(b["end"], 3) for b in src}
        for i, b in enumerate(blocks):
            pos = "#%d %s" % (i + 1, b["time_line"])
            if round(b["start"], 3) not in src_starts:
                errors.append("%s: start time does not exist in the source" % pos)
            if round(b["end"], 3) not in src_ends:
                errors.append("%s: end time does not exist in the source" % pos)
            covered = [s for s in src if s["start"] >= b["start"] - 1e-6 and s["end"] <= b["end"] + 1e-6]
            if len(covered) >= 3:
                notes.append("%s: merges %d source blocks — re-audit each removed boundary" % (pos, len(covered)))
        if merge_intervals(blocks) != merge_intervals(src):
            errors.append(
                "timeline coverage differs from the source: some text was dropped, "
                "duplicated, or re-timed"
            )
        kept = 100.0 * len(blocks) / max(len(src), 1)
        notes.append("blocks: %d source -> %d output (%.0f%% kept)" % (len(src), len(blocks), kept))
        if kept < 70:
            warnings.append(
                "output kept only %.0f%% of the source blocks — check for over-merging" % kept
            )
    return blocks, errors, warnings, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="translated .srt to check")
    ap.add_argument("--source", help="original .srt to compare against")
    ap.add_argument("--max-cps", type=float, default=DEFAULTS["max_cps"])
    ap.add_argument("--min-duration", type=float, default=DEFAULTS["min_duration"])
    ap.add_argument("--max-duration", type=float, default=DEFAULTS["max_duration"])
    ap.add_argument("--max-lines", type=int, default=DEFAULTS["max_lines"],
                    help="lines allowed per block; 1 by default, raise to 2 for bilingual output")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="only print errors and the summary")
    args = ap.parse_args()

    cfg = {
        "max_cps": args.max_cps,
        "min_duration": args.min_duration,
        "max_duration": args.max_duration,
        "max_lines": args.max_lines,
    }
    blocks, errors, warnings, notes = check(args.output, args.source, cfg)

    if args.json:
        print(json.dumps(
            {"blocks": len(blocks), "errors": errors, "warnings": warnings, "notes": notes},
            ensure_ascii=False, indent=2))
    else:
        for label, items in (("ERROR", errors), ("WARN", warnings), ("NOTE", notes)):
            if label != "ERROR" and args.quiet:
                continue
            for item in items:
                print("[%s] %s" % (label, item))
        print("\n%d blocks | %d errors | %d warnings | %d notes"
              % (len(blocks), len(errors), len(warnings), len(notes)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
