#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_subtitle.py — structural and readability validator for translated subtitle files.

Supports SRT (.srt), WebVTT (.vtt), and ASS/SSA (.ass/.ssa). The format is detected
from the file extension; the output and the --source file must share one format —
silent format conversion is itself an error.

    python check_subtitle.py out-zh.srt                     # check one file
    python check_subtitle.py out-zh.srt --source in.srt     # also diff against the source
    python check_subtitle.py out.en.srt --lang en           # non-Chinese target language

Checks performed on the output file:
  - parseable; SRT indices sequential from 1; no empty text block
  - start < end; no overlap with the following block (a warning, not an error, for
    ASS, where layered or positioned events may overlap legitimately)
  - duration below/above comfort thresholds, characters-per-second load using the
    target language's reading-speed anchor (--lang, default zh)
  - per-line scan width beyond the one-glance comfort zone (split or condense)
  - one line per block — wrapping is not allowed; ASS \\N breaks count as lines
  - disallowed trailing punctuation at end of a line (CJK targets only; question
    marks remain valid, exclamation marks are forbidden)
  - forbidden exclamation marks in subtitle text ('！' and '!')
  - internal full stops and semicolons that may indicate two thought units were
    placed in one Chinese subtitle block
  - missing space between CJK and Latin/digits (zh target only; reported, not fatal)

Extra checks when --source is given:
  - the audio is treated as the contract: source gaps >= 0.3s are real pauses;
    source blocks bridged by smaller gaps form continuous speech spans
  - no output block crosses a real pause or lies outside source speech
  - every speech span is fully covered: pieces tile it from start to end with no
    uncovered speech; boundaries inside a span may be re-placed (merges and
    target-language re-splits are legal and reported as notes)
  - pass --strict to additionally require every block edge to pre-exist in the
    source (timeline byte-for-byte untouched)
  - block-count delta and the merge factor of each output block

Exit code 0 = no errors (warnings may still be printed), 1 = errors found.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

# Subtitle text is often CJK; never let a legacy console codepage mangle the report.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
VTT_TIME_RE = re.compile(
    r"^(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})(.*)$"
)
ASS_TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")

# Markup carries no reading load: HTML-style tags (SRT/VTT), VTT voice/class/karaoke
# tags, and ASS override blocks are stripped before measuring text.
MARKUP_RE = re.compile(r"<[^>]*>|\{\\[^}]*\}")

# Duration bounds follow the Netflix Timed Text Style Guides and are language-
# independent; the reading-speed anchor and scan-comfort width are per target
# language. "cjk" counting: a full-width char costs 1, a Latin letter/digit 0.5,
# punctuation is free. "raw" counting: every character including spaces costs 1,
# the conventional way Latin-script cps is measured. max_width is the one-glance
# scan-comfort threshold — a review trigger for splitting/condensing, not a quota.
# These are calibration anchors, not a scoring rubric — override from the command
# line when a project has its own spec.
DEFAULTS = {
    "min_duration": 0.833,    # seconds; 20 frames @24fps — shorter blocks flash by unread
    "max_duration": 7.0,      # seconds; longer blocks feel stuck on screen
    "max_lines": 1,           # bilingual and multi-speaker output may raise this
    "min_split_piece": 1.0,   # seconds; a readability-split piece must not flash by
}
LANG_PROFILES = {
    "zh":      {"max_cps": 9.0,  "max_width": 25, "counting": "cjk", "final_punct": True,  "spacing": True,  "ban_exclamation": True},
    "zh-hant": {"max_cps": 9.0,  "max_width": 25, "counting": "cjk", "final_punct": True,  "spacing": True,  "ban_exclamation": True},
    "ja":      {"max_cps": 4.0,  "max_width": 25, "counting": "cjk", "final_punct": True,  "spacing": False, "ban_exclamation": True},
    "ko":      {"max_cps": 12.0, "max_width": 25, "counting": "cjk", "final_punct": False, "spacing": False, "ban_exclamation": False},
    "en":      {"max_cps": 20.0, "max_width": 42, "counting": "raw", "final_punct": False, "spacing": False, "ban_exclamation": False},
    "default": {"max_cps": 17.0, "max_width": 42, "counting": "raw", "final_punct": False, "spacing": False, "ban_exclamation": False},
}

DISALLOWED_TRAILING_PUNCT = "。．.;；:：、,，！!"
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿぀-ヿ]")
LATIN_RE = re.compile(r"[A-Za-z0-9]")
INTERNAL_SEGMENTATION_MARKS = ("。", "；")
# ==============================================================================
# Syntactic Boundary & Thought-Unit Cohesion Engine (ZH/CJK)
# ==============================================================================
# A robust subtitle block must be a self-contained "thought unit" / "breath group".
# Rather than static string matching, boundaries in continuous speech are validated
# against universal functional grammatical categories to detect broken dependencies:
#
# 1. Clausal Connectives & Transitionals (must introduce the next clause, not hang at tail)
# 2. Prepositions & Case Markers (must precede their object in the next block)
# 3. Governing / Serial Introductory Verbs (verbs that take a clausal/VP complement)
# 4. Structural & Aspectual Particles (must attach to their head, never stranded at head)
# 5. Demonstratives & Classifiers (must not be separated from their head noun)
# ==============================================================================

GRAMMAR_CATEGORIES_ZH = {
    # 关联/转折/因果/假设等从句引导范畴（连词必须前置于分句）
    "clausal_connectives": (
        "因为", "所以", "如果", "要是", "假如", "假若", "倘若", "虽然", "尽管", "哪怕", "即使",
        "但是", "但", "然而", "可是", "不过", "然后", "接着", "而且", "并且", "以及", "此外",
        "无论是", "无论", "不管", "不仅是", "不仅", "也就是说", "其实就是", "换句话说", "由于",
    ),
    # 介词与格标记范畴（介宾结构禁止跨块切断）
    "prepositions": (
        "关于", "对于", "至于", "包括", "比如像", "就像", "比如", "类似于", "根据", "按照",
        "通过", "为了", "以便", "把", "让", "给", "被", "由", "向", "往", "朝", "从",
    ),
    # 支配性引入动词/连动式引导动词（带从句/谓词性宾语的动词，必须归入后一从句或与前句整句闭合）
    "governing_verbs": (
        "看看这个", "看看能不能", "看看能否", "去看看", "去看", "试试看", "来看看", "来看", "看看", "看",
        "试试", "准备去", "准备", "想要", "希望", "打算", "负责", "用来做", "用来进行", "用来",
        "试图", "开始", "尝试", "负责", "旨在", "意味着", "导致", "造成", "使得",
        "回到", "归到", "变成", "设成", "叫做", "弄成", "转成",
    ),
    # 指示代词与量词修饰范畴（定中结构禁止分离）
    "specifiers_and_classifiers": (
        "一种", "一条", "一份", "一段", "一位", "一个", "一些", "某种", "某位", "某个",
    ),
}

# 组合所有句尾悬空禁止词族（编译为高效的正则表达式）
ALL_TAIL_DANGLING_ZH = (
    GRAMMAR_CATEGORIES_ZH["clausal_connectives"]
    + GRAMMAR_CATEGORIES_ZH["prepositions"]
    + GRAMMAR_CATEGORIES_ZH["governing_verbs"]
    + GRAMMAR_CATEGORIES_ZH["specifiers_and_classifiers"]
)

# 句首悬空助词/附着标记范畴（禁止孤立出现在下句开头）
DANGLING_HEAD_PARTICLES_ZH = (
    "的", "地", "得", "之类", "等等", "一样", "一般", "似的", "左右", "上下", "前后"
)
PUNCT_CATEGORIES = {"P", "S", "Z", "C"}

EXT_FORMATS = {".srt": "srt", ".vtt": "vtt", ".ass": "ass", ".ssa": "ass"}


def detect_format(path, override):
    if override:
        return override
    fmt = EXT_FORMATS.get(os.path.splitext(path)[1].lower())
    if not fmt:
        raise SystemExit("cannot detect format of %s — pass --format srt|vtt|ass" % path)
    return fmt


def read_text(path):
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
    return text.replace("\r\n", "\n").replace("\r", "\n")


def to_seconds(h, m, s, frac, frac_unit=1000.0):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(frac) / frac_unit


def fmt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def make_block(index, start, end, time_line, lines):
    return {"index": index, "start": start, "end": end,
            "time_line": time_line, "lines": lines}


def parse_srt(text):
    blocks, errors = [], []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in chunk.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        idx_line, time_pos = None, 0
        if SRT_TIME_RE.match(lines[0]):
            time_pos = 0
        elif len(lines) > 1 and SRT_TIME_RE.match(lines[1]):
            idx_line, time_pos = lines[0].strip(), 1
        else:
            errors.append("unparseable block near: %s" % lines[0][:60])
            continue
        m = SRT_TIME_RE.match(lines[time_pos])
        blocks.append(make_block(
            int(idx_line) if idx_line and idx_line.isdigit() else None,
            to_seconds(m.group(1), m.group(2), m.group(3), m.group(4)),
            to_seconds(m.group(5), m.group(6), m.group(7), m.group(8)),
            lines[time_pos].strip(), lines[time_pos + 1:]))
    return blocks, errors


def parse_vtt(text):
    blocks, errors = [], []
    chunks = re.split(r"\n\s*\n", text.strip())
    if not chunks or not chunks[0].lstrip("﻿").startswith("WEBVTT"):
        errors.append("file does not start with a WEBVTT header")
    else:
        chunks = chunks[1:]
    for chunk in chunks:
        lines = [ln for ln in chunk.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        # NOTE/STYLE/REGION blocks are structure, not cues — preserved, not checked.
        if lines[0].split()[0] in ("NOTE", "STYLE", "REGION"):
            continue
        time_pos = 0 if "-->" in lines[0] else 1
        if time_pos >= len(lines) or not VTT_TIME_RE.match(lines[time_pos]):
            errors.append("unparseable cue near: %s" % lines[0][:60])
            continue
        m = VTT_TIME_RE.match(lines[time_pos])
        blocks.append(make_block(
            None,
            to_seconds(m.group(1), m.group(2), m.group(3), m.group(4)),
            to_seconds(m.group(5), m.group(6), m.group(7), m.group(8)),
            lines[time_pos].strip(), lines[time_pos + 1:]))
    return blocks, errors


def parse_ass(text):
    blocks, errors = [], []
    fields, in_events = None, False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith("["):
            in_events = line.lower() == "[events]"
            continue
        if not in_events or not line:
            continue
        if line.lower().startswith("format:"):
            fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
            continue
        if not line.lower().startswith("dialogue:"):
            continue  # Comment/Picture/Sound events are preserved, not checked
        if not fields or "start" not in fields or "end" not in fields or "text" not in fields:
            errors.append("Dialogue line before a usable Format line: %s" % line[:60])
            continue
        parts = line.split(":", 1)[1].split(",", len(fields) - 1)
        if len(parts) < len(fields):
            errors.append("Dialogue line with too few fields: %s" % line[:60])
            continue
        ms = ASS_TIME_RE.match(parts[fields.index("start")].strip())
        me = ASS_TIME_RE.match(parts[fields.index("end")].strip())
        if not ms or not me:
            errors.append("bad ASS timestamp in: %s" % line[:60])
            continue
        start = to_seconds(ms.group(1), ms.group(2), ms.group(3), ms.group(4), 100.0)
        end = to_seconds(me.group(1), me.group(2), me.group(3), me.group(4), 100.0)
        text_field = parts[fields.index("text")]
        blocks.append(make_block(
            None, start, end,
            "%s --> %s" % (parts[fields.index("start")].strip(),
                           parts[fields.index("end")].strip()),
            re.split(r"\\[Nn]", text_field)))
    if not blocks and not errors:
        errors.append("no Dialogue lines found in the [Events] section")
    return blocks, errors


PARSERS = {"srt": parse_srt, "vtt": parse_vtt, "ass": parse_ass}


def parse_file(path, fmt):
    return PARSERS[fmt](read_text(path))


def display_width(text, counting):
    """Reading cost of a line, markup stripped.

    cjk: full-width chars cost 1, Latin letters/digits 0.5, punctuation free.
    raw: every character costs 1, including spaces (conventional Latin cps).
    """
    text = MARKUP_RE.sub("", text)
    if counting == "raw":
        return float(len(text.strip()))
    total = 0.0
    for ch in text:
        if unicodedata.category(ch)[0] in PUNCT_CATEGORIES:
            continue
        total += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
    return total


def check(out_path, src_path, fmt, src_fmt, cfg):
    errors, warnings, notes = [], [], []
    blocks, parse_errors = parse_file(out_path, fmt)
    errors.extend(parse_errors)
    if not blocks:
        errors.append("no subtitle blocks found in %s" % out_path)
        return blocks, errors, warnings, notes

    for i, b in enumerate(blocks):
        pos = "#%d %s" % (i + 1, b["time_line"])
        if fmt == "srt" and b["index"] is not None and b["index"] != i + 1:
            errors.append("%s: index is %s, expected %d" % (pos, b["index"], i + 1))
        text = " ".join(b["lines"]).strip()
        if not MARKUP_RE.sub("", text).strip():
            errors.append("%s: empty subtitle text" % pos)
            continue
        if b["end"] <= b["start"]:
            errors.append("%s: end time is not after start time" % pos)
        if i + 1 < len(blocks) and blocks[i + 1]["start"] < b["end"] - 1e-6:
            msg = "%s: overlaps the next block" % pos
            if fmt == "ass":
                warnings.append(msg + " — fine if the events are layered signs/dialogue")
            else:
                errors.append(msg)

        dur = max(b["end"] - b["start"], 1e-6)
        width = display_width(text, cfg["counting"])
        cps = width / dur
        if dur < cfg["min_duration"]:
            warnings.append("%s: only %.2fs on screen — %s" % (pos, dur, text[:30]))
        if dur > cfg["max_duration"]:
            warnings.append("%s: %.1fs on screen, longer than %.1fs" % (pos, dur, cfg["max_duration"]))
        if cps > cfg["max_cps"]:
            warnings.append(
                "%s: %.1f chars/s (limit %.1f for lang=%s), %.0f chars in %.2fs — %s"
                % (pos, cps, cfg["max_cps"], cfg["lang"], width, dur, text[:30])
            )
        line_width = max((display_width(ln, cfg["counting"]) for ln in b["lines"]), default=0.0)
        if line_width > cfg["max_width"]:
            warnings.append(
                "%s: line spans %.0f chars — beyond the one-glance comfort zone (%.0f for "
                "lang=%s); split at a thought-unit boundary or condense — %s"
                % (pos, line_width, cfg["max_width"], cfg["lang"], text[:30])
            )
        if len(b["lines"]) > cfg["max_lines"]:
            warnings.append(
                "%s: %d lines — a block is one line; condense the text instead of wrapping it"
                % (pos, len(b["lines"]))
            )
        if cfg["final_punct"]:
            for ln in b["lines"]:
                stripped = MARKUP_RE.sub("", ln).rstrip()
                if stripped and stripped[-1] in DISALLOWED_TRAILING_PUNCT:
                    warnings.append("%s: line ends with '%s'" % (pos, stripped[-1]))
        if cfg.get("ban_exclamation"):
            for ln in b["lines"]:
                plain = MARKUP_RE.sub("", ln).strip()
                if not plain:
                    continue
                if "！" in plain or "!" in plain:
                    warnings.append(
                        "%s: contains exclamation mark ('！'/'!') — forbidden in subtitles; rewrite or remove"
                        % pos
                    )
        if cfg["lang"] in ("zh", "zh-hant"):
            for ln in b["lines"]:
                plain = MARKUP_RE.sub("", ln).strip()
                if not plain:
                    continue
                for mark in INTERNAL_SEGMENTATION_MARKS:
                    start = 0
                    while True:
                        at = plain.find(mark, start)
                        if at < 0:
                            break
                        is_line_end = at == len(plain) - 1
                        if not is_line_end:
                            warnings.append(
                                "%s: internal '%s' — review whether a rephrase or split reads better"
                                % (pos, mark)
                            )
                        start = at + 1
        if cfg["spacing"]:
            for m in re.finditer(r"(?:%s)(?:%s)|(?:%s)(?:%s)"
                                 % (CJK_RE.pattern, LATIN_RE.pattern,
                                    LATIN_RE.pattern, CJK_RE.pattern), text):
                notes.append("%s: missing space at '%s'" % (pos, m.group(0)))

        if cfg["lang"] in ("zh", "zh-hant") and i + 1 < len(blocks):
            nxt_b = blocks[i + 1]
            gap = nxt_b["start"] - b["end"]
            # In continuous speech (gap < 0.6s), check for fractured thought units
            if gap < 0.6:
                clean_text = MARKUP_RE.sub("", text).rstrip(" 。．,.;；：、，！？! ")
                
                # Check for dangling clausal connectives, prepositions, or governing verbs at tail
                for w in ALL_TAIL_DANGLING_ZH:
                    if (clean_text.endswith(w) or clean_text.endswith(" " + w)) and clean_text != w:
                        warnings.append(
                            "%s: thought-unit boundary broken — ends on dangling %s '%s' before #%d; "
                            "move '%s' to the start of the next block or merge"
                            % (pos, "connector/verb", w, i + 2, w)
                        )
                        break
                
                # Check for stranded dependent particles at head of continuation block
                nxt_text = " ".join(nxt_b["lines"]).strip()
                nxt_clean = MARKUP_RE.sub("", nxt_text).lstrip()
                for p in DANGLING_HEAD_PARTICLES_ZH:
                    if nxt_clean.startswith(p):
                        if len(nxt_clean) > len(p) and not nxt_clean[len(p)].isspace():
                            next_pos = "#%d %s" % (i + 2, nxt_b["time_line"])
                            warnings.append(
                                "%s: thought-unit boundary broken — starts with stranded particle '%s' from #%d; "
                                "attach to preceding phrase or rebalance"
                                % (next_pos, p, i + 1)
                            )
                            break

    if src_path:
        if src_fmt != fmt:
            errors.append(
                "source is %s but output is %s — formats must match; converting "
                "requires an explicit user request and cannot be verified here"
                % (src_fmt, fmt))
            return blocks, errors, warnings, notes
        src, src_parse_errors = parse_file(src_path, src_fmt)
        errors.extend("source: " + e for e in src_parse_errors)
        src_starts = {round(b["start"], 3) for b in src}
        src_ends = {round(b["end"], 3) for b in src}
        TOL = 0.002
        # The audio is the contract: gaps >= SMALL_GAP are real pauses that must
        # survive; boundaries inside a continuous speech span may be re-placed to
        # fit target-language phrasing, as long as the pieces tile the span.
        SMALL_GAP = 0.3
        segs = []
        for s0, e0 in sorted((b["start"], b["end"]) for b in src):
            if segs and s0 <= segs[-1][1] + SMALL_GAP:
                segs[-1][1] = max(segs[-1][1], e0)
            else:
                segs.append([s0, e0])
        seg_pieces = [[] for _ in segs]
        new_edges = 0
        for i, b in enumerate(blocks):
            pos = "#%d %s" % (i + 1, b["time_line"])
            ok_start = round(b["start"], 3) in src_starts
            ok_end = round(b["end"], 3) in src_ends
            new_edges += (not ok_start) + (not ok_end)
            if cfg["strict"]:
                if not ok_start:
                    errors.append("%s: start time does not exist in the source (strict)" % pos)
                if not ok_end:
                    errors.append("%s: end time does not exist in the source (strict)" % pos)
            parent = next((j for j, (ss, se) in enumerate(segs)
                           if ss - TOL <= b["start"] and b["end"] <= se + TOL), None)
            if parent is None:
                errors.append("%s: block crosses a real pause (>= %.1fs of silence) or "
                              "lies outside source speech" % (pos, SMALL_GAP))
                continue
            seg_pieces[parent].append(b)
            if (not ok_start or not ok_end) and b["end"] - b["start"] < cfg["min_split_piece"] - TOL:
                warnings.append("%s: re-placed piece is only %.2fs — the boundary sits in "
                                "the wrong place or the split was unnecessary"
                                % (pos, b["end"] - b["start"]))
            covered = [s for s in src if s["start"] >= b["start"] - TOL and s["end"] <= b["end"] + TOL]
            if len(covered) >= 3:
                notes.append("%s: merges %d source blocks — re-audit each removed boundary" % (pos, len(covered)))
        for j, pieces in enumerate(seg_pieces):
            ss, se = segs[j]
            span = "%s --> %s" % (fmt_time(ss), fmt_time(se))
            if not pieces:
                errors.append("speech span %s has no subtitles — its text was dropped" % span)
                continue
            pieces.sort(key=lambda b: b["start"])
            if pieces[0]["start"] > ss + TOL:
                errors.append("speech span %s: speech at the start is uncovered" % span)
            if pieces[-1]["end"] < se - TOL:
                errors.append("speech span %s: speech at the end is uncovered" % span)
            for a, b2 in zip(pieces, pieces[1:]):
                if b2["start"] - a["end"] > SMALL_GAP + TOL:
                    errors.append("speech span %s: %.2fs of speech uncovered before %s"
                                  % (span, b2["start"] - a["end"], b2["time_line"]))
        if new_edges:
            notes.append("%d block edges re-placed to fit target-language phrasing" % new_edges)
        kept = 100.0 * len(blocks) / max(len(src), 1)
        notes.append("blocks: %d source -> %d output (%.0f%% kept)" % (len(src), len(blocks), kept))
        if kept < 70:
            warnings.append(
                "output kept only %.0f%% of the source blocks — check for over-merging" % kept
            )
    return blocks, errors, warnings, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="translated subtitle file to check (.srt/.vtt/.ass)")
    ap.add_argument("--source", help="original subtitle file to compare against")
    ap.add_argument("--lang", default="zh",
                    help="target language code for reading-speed and punctuation rules: "
                         "%s; anything else uses the Latin-script default"
                         % "/".join(k for k in LANG_PROFILES if k != "default"))
    ap.add_argument("--format", choices=("srt", "vtt", "ass"),
                    help="override format detection for both files")
    ap.add_argument("--max-cps", type=float, help="override the language's reading-speed limit")
    ap.add_argument("--max-width", type=float,
                    help="override the language's one-glance scan-comfort threshold")
    ap.add_argument("--strict", action="store_true",
                    help="require every output edge to pre-exist in the source (timeline untouched)")
    ap.add_argument("--min-duration", type=float, default=DEFAULTS["min_duration"])
    ap.add_argument("--max-duration", type=float, default=DEFAULTS["max_duration"])
    ap.add_argument("--max-lines", type=int, default=DEFAULTS["max_lines"],
                    help="lines allowed per block; 1 by default, raise to 2 for bilingual output")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="only print errors and the summary")
    args = ap.parse_args()

    lang = args.lang.lower()
    profile = LANG_PROFILES.get(lang, LANG_PROFILES["default"])
    cfg = {
        "lang": lang,
        "max_cps": args.max_cps if args.max_cps else profile["max_cps"],
        "max_width": args.max_width if args.max_width else profile["max_width"],
        "counting": profile["counting"],
        "final_punct": profile["final_punct"],
        "ban_exclamation": profile.get("ban_exclamation", False),
        "spacing": profile["spacing"],
        "strict": args.strict,
        "min_duration": args.min_duration,
        "max_duration": args.max_duration,
        "max_lines": args.max_lines,
        "min_split_piece": DEFAULTS["min_split_piece"],
    }
    fmt = detect_format(args.output, args.format)
    src_fmt = detect_format(args.source, args.format) if args.source else None
    blocks, errors, warnings, notes = check(args.output, args.source, fmt, src_fmt, cfg)

    if args.json:
        print(json.dumps(
            {"format": fmt, "lang": lang, "blocks": len(blocks),
             "errors": errors, "warnings": warnings, "notes": notes},
            ensure_ascii=False, indent=2))
    else:
        for label, items in (("ERROR", errors), ("WARN", warnings), ("NOTE", notes)):
            if label != "ERROR" and args.quiet:
                continue
            for item in items:
                print("[%s] %s" % (label, item))
        print("\n%s | %d blocks | %d errors | %d warnings | %d notes"
              % (fmt, len(blocks), len(errors), len(warnings), len(notes)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
