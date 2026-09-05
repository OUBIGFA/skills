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
  - source gaps at or above the configured pause proxy form separate speech spans;
    smaller gaps may be preserved or re-placed
  - no output block crosses a real pause or lies outside source speech
  - every speech span is fully covered: pieces tile it from start to end with no
    uncovered speech; boundaries inside a span may be re-placed (merges and
    target-language re-splits are legal and reported as notes)
  - length fidelity: how much text each speech span carries compared with the
    source, to surface padding (words the audio never had) and dropped payload
  - pass --strict to additionally require every block edge to pre-exist in the
    source (timeline byte-for-byte untouched)
  - block-count delta and the merge factor of each output block

Exit code 0 = no errors (warnings may still be printed), 1 = errors found.
"""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import statistics
import sys
import unicodedata

# Subtitle text is often CJK; never let a legacy console codepage mangle the report.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)
VTT_TIME_RE = re.compile(
    r"^(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})(?:\s+.*)?$"
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
    "pause_gap": 0.3,         # seconds; source subtitle gap used as a pause proxy
}

# Length-fidelity calibration. Padding (words the audio never had) and dropped
# payload both show up as one speech span carrying far more or far less text than
# the rest of the file does for the same amount of source text. The comparison is
# made against the file's own median ratio, so it self-calibrates to the language
# pair, the speaker's density, and bilingual output — no per-language constant.
FIDELITY = {
    "min_span_cost": 6.0,   # source text volume below this is too small to judge
    "min_spans": 8,         # fewer usable spans than this: no reliable median
    "pad_factor": 1.6,      # ratio above median * this: suspect padding
    "drop_factor": 0.6,     # ratio below median * this: suspect dropped content
    "max_reports": 12,      # worst offenders only — a wall of warnings gets ignored
}

DEFAULT_LANGUAGE_CONFIG = str(
    Path(__file__).resolve().parents[1] / "config" / "language_profiles.json"
)


def load_language_profiles(path):
    """Load and validate language-specific reading and punctuation settings."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            profiles = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot load language configuration %s: %s" % (path, exc)) from exc

    required = {"target_language", "counting", "final_punctuation", "max_cps", "max_width"}
    if not isinstance(profiles, dict) or "default" not in profiles:
        raise ValueError("language configuration must be an object with a default profile")
    for code, profile in profiles.items():
        if not isinstance(profile, dict) or not required.issubset(profile):
            raise ValueError("language profile %s is missing required fields" % code)
        if profile["counting"] not in ("cjk", "raw"):
            raise ValueError("language profile %s has unsupported counting mode" % code)
        if profile["final_punctuation"] not in ("none", "standard"):
            raise ValueError("language profile %s has unsupported final punctuation mode" % code)
        if float(profile["max_cps"]) <= 0 or float(profile["max_width"]) <= 0:
            raise ValueError("language profile %s has non-positive reading limits" % code)
    return profiles


def get_language_profile(lang, profiles=None):
    """Resolve an exact or regional language code, then fall back explicitly."""
    profiles = profiles or LANG_PROFILES
    normalized = (lang or "default").lower().replace("_", "-")
    if normalized in profiles:
        return profiles[normalized]
    base = normalized.split("-", 1)[0]
    return profiles.get(base, profiles["default"])


def language_profile_resolution(lang, profiles=None):
    """Return the profile and the code that supplied it."""
    profiles = profiles or LANG_PROFILES
    normalized = (lang or "default").lower().replace("_", "-")
    if normalized in profiles:
        return profiles[normalized], normalized
    base = normalized.split("-", 1)[0]
    if base in profiles:
        return profiles[base], base
    return profiles["default"], "default"


LANG_PROFILES = load_language_profiles(DEFAULT_LANGUAGE_CONFIG)

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


def read_text(path, require_utf8=False):
    with open(path, "rb") as fh:
        raw = fh.read()
    if require_utf8:
        try:
            return raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError as exc:
            raise ValueError("%s must be UTF-8 (UTF-8 BOM is allowed)" % path) from exc

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16", "utf-16-le", "utf-16-be")
    elif b"\x00" in raw:
        encodings = ("utf-16-le", "utf-16-be", "utf-8-sig", "utf-8", "gb18030")
    else:
        encodings = ("utf-8-sig", "utf-8", "gb18030", "utf-16")
    for enc in encodings:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("cannot decode %s as utf-8/gb18030/utf-16" % path)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def valid_clock(h, m, s):
    return 0 <= int(m) < 60 and 0 <= int(s) < 60


def to_seconds(h, m, s, frac, frac_unit=1000.0):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(frac) / frac_unit


def fmt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def make_block(index, start, end, time_line, lines, **metadata):
    block = {"index": index, "start": start, "end": end,
             "time_line": time_line, "lines": lines}
    block.update(metadata)
    return block


def parse_srt(text):
    blocks, errors = [], []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in chunk.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        idx_line, time_pos = None, 0
        if SRT_TIME_RE.match(lines[0]):
            errors.append("SRT block is missing a sequential index near: %s" % lines[0][:60])
            time_pos = 0
        elif len(lines) > 1 and SRT_TIME_RE.match(lines[1]):
            idx_line, time_pos = lines[0].strip(), 1
            if not idx_line.isdigit():
                errors.append("invalid SRT index near: %s" % lines[0][:60])
        else:
            errors.append("unparseable block near: %s" % lines[0][:60])
            continue
        m = SRT_TIME_RE.match(lines[time_pos])
        if not valid_clock(m.group(1), m.group(2), m.group(3)):
            errors.append("invalid SRT timestamp near: %s" % lines[time_pos][:60])
        if not valid_clock(m.group(5), m.group(6), m.group(7)):
            errors.append("invalid SRT timestamp near: %s" % lines[time_pos][:60])
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
        if lines[0].split()[0].upper() in ("NOTE", "STYLE", "REGION"):
            continue
        time_pos = 0 if "-->" in lines[0] else 1
        if time_pos >= len(lines) or not VTT_TIME_RE.match(lines[time_pos]):
            errors.append("unparseable cue near: %s" % lines[0][:60])
            continue
        m = VTT_TIME_RE.match(lines[time_pos])
        if not valid_clock(m.group(1), m.group(2), m.group(3)):
            errors.append("invalid VTT timestamp near: %s" % lines[time_pos][:60])
        if not valid_clock(m.group(5), m.group(6), m.group(7)):
            errors.append("invalid VTT timestamp near: %s" % lines[time_pos][:60])
        settings = lines[time_pos][m.end(8):].strip() if m.end(8) < len(lines[time_pos]) else ""
        blocks.append(make_block(
            None,
            to_seconds(m.group(1), m.group(2), m.group(3), m.group(4)),
            to_seconds(m.group(5), m.group(6), m.group(7), m.group(8)),
            lines[time_pos].strip(), lines[time_pos + 1:],
            cue_id=lines[0].strip() if time_pos == 1 else None,
            cue_settings=settings))
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
        if not valid_clock(ms.group(1), ms.group(2), ms.group(3)):
            errors.append("invalid ASS timestamp in: %s" % line[:60])
        if not valid_clock(me.group(1), me.group(2), me.group(3)):
            errors.append("invalid ASS timestamp in: %s" % line[:60])
        start = to_seconds(ms.group(1), ms.group(2), ms.group(3), ms.group(4), 100.0)
        end = to_seconds(me.group(1), me.group(2), me.group(3), me.group(4), 100.0)
        text_field = parts[fields.index("text")]
        blocks.append(make_block(
            None, start, end,
            "%s --> %s" % (parts[fields.index("start")].strip(),
                           parts[fields.index("end")].strip()),
            re.split(r"\\[Nn]", text_field),
            ass_fields=dict(zip(fields, parts)),
            ass_non_text=tuple(parts[i] for i, field in enumerate(fields)
                               if field not in ("start", "end", "text"))))
    if not blocks and not errors:
        errors.append("no Dialogue lines found in the [Events] section")
    return blocks, errors


PARSERS = {"srt": parse_srt, "vtt": parse_vtt, "ass": parse_ass}


def parse_file(path, fmt, require_utf8=False):
    return PARSERS[fmt](read_text(path, require_utf8=require_utf8))


PROTECTED_MARKUP_RE = re.compile(r"<[^>]*>|\{\\[^}]*\}|\\[NnHh]")


def protected_markup_signature(text):
    return Counter(PROTECTED_MARKUP_RE.findall(text))


def vtt_structure(text):
    chunks = re.split(r"\n\s*\n", text.strip())
    header = chunks[0].strip() if chunks else ""
    static = []
    for chunk in chunks[1:]:
        lines = [ln for ln in chunk.split("\n") if ln.strip()]
        if lines and lines[0].split()[0].upper() in ("NOTE", "STYLE", "REGION"):
            static.append(chunk.strip())
    return header, tuple(static)


def ass_structure(text):
    static = []
    for line in text.split("\n"):
        if not line.lstrip().lower().startswith("dialogue:"):
            static.append(line)
    return tuple(static)


def overlapping_source_blocks(source_blocks, output_block):
    """Return source events touched by an output interval, in source order."""
    tolerance = 0.002
    return [
        source for source in sorted(source_blocks, key=lambda block: block["start"])
        if source["end"] > output_block["start"] + tolerance
        and source["start"] < output_block["end"] - tolerance
    ]


def compare_structure(source_text, output_text, fmt, source_blocks, output_blocks, strict):
    """Check non-dialogue structure and protected markup without judging translation wording."""
    errors = []
    if fmt == "vtt":
        source_header, source_static = vtt_structure(source_text)
        output_header, output_static = vtt_structure(output_text)
        if source_header != output_header:
            errors.append("VTT header metadata changed")
        if source_static != output_static:
            errors.append("VTT NOTE/STYLE/REGION structure changed")
        source_ids = [b.get("cue_id") for b in source_blocks if b.get("cue_id")]
        output_ids = [b.get("cue_id") for b in output_blocks if b.get("cue_id")]
        source_settings = [b.get("cue_settings", "") for b in source_blocks if b.get("cue_settings")]
        output_settings = [b.get("cue_settings", "") for b in output_blocks if b.get("cue_settings")]
        if source_ids and not output_ids:
            errors.append("VTT cue identifiers were removed")
        if len(output_ids) != len(set(output_ids)):
            errors.append("VTT cue identifier is duplicated")
        if any(identifier not in source_ids for identifier in output_ids):
            errors.append("VTT cue identifier changed")
        if source_settings and not output_settings:
            errors.append("VTT cue settings were removed")
        if any(settings not in source_settings for settings in output_settings):
            errors.append("VTT cue settings changed")
        for position, output in enumerate(output_blocks, 1):
            covered = overlapping_source_blocks(source_blocks, output)
            if not covered:
                continue
            first = covered[0]
            if output.get("cue_id") != first.get("cue_id"):
                errors.append(
                    "VTT cue #%d identifier does not match the first covered source cue"
                    % position
                )
            if output.get("cue_settings", "") != first.get("cue_settings", ""):
                errors.append(
                    "VTT cue #%d settings do not match the first covered source cue"
                    % position
                )
    elif fmt == "ass":
        if ass_structure(source_text) != ass_structure(output_text):
            errors.append("ASS non-Dialogue structure changed")
        source_non_text = Counter(b.get("ass_non_text", ()) for b in source_blocks)
        output_non_text = Counter(b.get("ass_non_text", ()) for b in output_blocks)
        if any(output_non_text[key] > source_non_text[key] for key in output_non_text):
            errors.append("ASS non-Text Dialogue fields changed")
        for position, output in enumerate(output_blocks, 1):
            covered = overlapping_source_blocks(source_blocks, output)
            if not covered:
                continue
            if output.get("ass_non_text") != covered[0].get("ass_non_text"):
                errors.append(
                    "ASS event #%d non-Text fields do not match the first covered source event"
                    % position
                )

    source_markup = protected_markup_signature(source_text)
    output_markup = protected_markup_signature(output_text)
    if source_markup != output_markup:
        errors.append("protected subtitle markup changed")

    if strict:
        if len(source_blocks) != len(output_blocks):
            errors.append("strict mode requires the source and output block counts to match")
        else:
            for index, (source, output) in enumerate(zip(source_blocks, output_blocks), 1):
                if source.get("time_line") != output.get("time_line"):
                    errors.append("strict block #%d changed its timestamp line" % index)
                if fmt == "srt" and source.get("index") != output.get("index"):
                    errors.append("strict block #%d changed its index" % index)
                if fmt == "vtt" and (
                    source.get("cue_id") != output.get("cue_id")
                    or source.get("cue_settings", "") != output.get("cue_settings", "")
                ):
                    errors.append("strict VTT cue #%d changed its identifier or settings" % index)
                if fmt == "ass" and source.get("ass_non_text") != output.get("ass_non_text"):
                    errors.append("strict ASS event #%d changed a non-Text field" % index)
    return errors


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


def block_text(block):
    return " ".join(block["lines"]).strip()


def text_volume(text):
    """Language-agnostic text volume, used to compare source and output length.

    Always the 'cjk' cost model so one number is comparable across scripts: a
    full-width char costs 1, a Latin letter/digit 0.5, punctuation nothing.
    """
    return display_width(text, "cjk")


def length_fidelity(segs, src_blocks, seg_pieces, cfg):
    """Flag speech spans whose translation is far longer or shorter than the file's norm.

    Padding — subjects, connectives and category nouns the audio never had — and
    dropped payload are both invisible to structural checks: the file still tiles
    the timeline perfectly. What gives them away is the ratio of translated text
    volume to source text volume drifting away from the ratio the rest of the file
    holds. Comparing each span against the file's own median makes this
    self-calibrating: it needs no constant per language pair, and bilingual output
    (which doubles every span) shifts the median rather than the verdict.
    """
    warnings, notes = [], []
    ratios = []
    for j, (ss, se) in enumerate(segs):
        src_cost = sum(text_volume(block_text(b)) for b in src_blocks
                       if b["start"] >= ss - 1e-6 and b["end"] <= se + 1e-6)
        out_cost = sum(text_volume(block_text(b)) for b in seg_pieces[j])
        if src_cost >= cfg["min_span_cost"] and out_cost > 0:
            ratios.append((out_cost / src_cost, j, src_cost, out_cost))
    if len(ratios) < cfg["min_spans"]:
        return warnings, notes  # too little material for a meaningful median

    median = statistics.median(r[0] for r in ratios)
    notes.append("length fidelity: median %.2f output chars per source char, "
                 "over %d speech spans" % (median, len(ratios)))
    pad_at, drop_at = median * cfg["pad_factor"], median * cfg["drop_factor"]
    flagged = []
    for ratio, j, src_cost, out_cost in ratios:
        if ratio > pad_at:
            flagged.append((ratio / median, j, ratio, out_cost, src_cost, "pad"))
        elif ratio < drop_at:
            flagged.append((median / ratio, j, ratio, out_cost, src_cost, "drop"))
    flagged.sort(reverse=True)
    for _, j, ratio, out_cost, src_cost, kind in flagged[:cfg["max_reports"]]:
        span = "%s --> %s" % (fmt_time(segs[j][0]), fmt_time(segs[j][1]))
        first = block_text(seg_pieces[j][0])[:30] if seg_pieces[j] else ""
        if kind == "pad":
            warnings.append(
                "speech span %s: %.0f output chars for %.0f source chars (%.1fx the "
                "file's %.2f norm) — check for padding the audio never had — %s"
                % (span, out_cost, src_cost, ratio / median, median, first))
        else:
            warnings.append(
                "speech span %s: only %.0f output chars for %.0f source chars (%.0f%% of "
                "the file's %.2f norm) — check for dropped payload — %s"
                % (span, out_cost, src_cost, 100.0 * ratio / median, median, first))
    return warnings, notes


def check(out_path, src_path, fmt, src_fmt, cfg):
    errors, warnings, notes = [], [], []
    try:
        out_text = read_text(out_path, require_utf8=True)
        blocks, parse_errors = PARSERS[fmt](out_text)
    except (OSError, ValueError) as exc:
        return [], [str(exc)], warnings, notes
    errors.extend(parse_errors)
    if not blocks:
        errors.append("no subtitle blocks found in %s" % out_path)
        return blocks, errors, warnings, notes

    for i, b in enumerate(blocks):
        pos = "#%d %s" % (i + 1, b["time_line"])
        if fmt == "srt" and b["index"] != i + 1:
            errors.append("%s: index is %s, expected %d" % (pos, b["index"], i + 1))
        if i > 0 and b["start"] < blocks[i - 1]["start"] - 1e-6:
            errors.append("%s: block is out of chronological order" % pos)
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
        if cfg.get("profile_code", cfg["lang"]) in ("zh", "zh-hant"):
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

        if cfg.get("profile_code", cfg["lang"]) in ("zh", "zh-hant") and i + 1 < len(blocks):
            nxt_b = blocks[i + 1]
            gap = nxt_b["start"] - b["end"]
            # In a continuous subtitle span, check for fractured thought units.
            if gap < cfg["pause_gap"]:
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
        try:
            src_text = read_text(src_path)
            src, src_parse_errors = PARSERS[src_fmt](src_text)
        except (OSError, ValueError) as exc:
            errors.append("source: " + str(exc))
            return blocks, errors, warnings, notes
        errors.extend("source: " + e for e in src_parse_errors)
        errors.extend(compare_structure(src_text, out_text, fmt, src, blocks, cfg["strict"]))
        if cfg["strict"] and len(src) == len(blocks):
            for index, (source_block, output_block) in enumerate(zip(src, blocks), 1):
                if (abs(source_block["start"] - output_block["start"]) > 0.001
                        or abs(source_block["end"] - output_block["end"]) > 0.001):
                    errors.append("strict block #%d changed its time boundary" % index)
        src_starts = {round(b["start"], 3) for b in src}
        src_ends = {round(b["end"], 3) for b in src}
        TOL = 0.002
        # A source subtitle gap is only a pause proxy. Gaps at or above the configured
        # threshold create separate spans; smaller gaps may be preserved or re-placed.
        SMALL_GAP = cfg["pause_gap"]
        segs = []
        for s0, e0 in sorted((b["start"], b["end"]) for b in src if b["end"] > b["start"]):
            if segs and s0 < segs[-1][1] + SMALL_GAP:
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
            source_gaps = []
            source_in_span = sorted(
                (b for b in src if b["start"] >= ss - TOL and b["end"] <= se + TOL),
                key=lambda b: b["start"],
            )
            for source_before, source_after in zip(source_in_span, source_in_span[1:]):
                gap_start, gap_end = source_before["end"], source_after["start"]
                if TOL < gap_end - gap_start < cfg["pause_gap"]:
                    source_gaps.append((gap_start, gap_end))
            for a, b2 in zip(pieces, pieces[1:]):
                gap_start, gap_end = a["end"], b2["start"]
                gap = gap_end - gap_start
                if gap > TOL and not any(
                    abs(gap_start - allowed_start) <= TOL
                    and abs(gap_end - allowed_end) <= TOL
                    for allowed_start, allowed_end in source_gaps
                ):
                    errors.append("speech span %s: %.2fs of speech uncovered before %s"
                                  % (span, gap, b2["time_line"]))
        if new_edges:
            notes.append("%d block edges re-placed to fit target-language phrasing" % new_edges)
        fid_warnings, fid_notes = length_fidelity(segs, src, seg_pieces, cfg)
        warnings.extend(fid_warnings)
        notes.extend(fid_notes)
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
                         "%s; regional codes use their base language and unknown codes use the explicit default profile"
                         % "/".join(k for k in LANG_PROFILES if k != "default"))
    ap.add_argument("--lang-config", default=DEFAULT_LANGUAGE_CONFIG,
                    help="JSON language profile file (default: %(default)s)")
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
    ap.add_argument("--pause-gap", type=float, default=DEFAULTS["pause_gap"],
                    help="source subtitle gap used as the pause proxy, in seconds")
    ap.add_argument("--pad-factor", type=float, default=FIDELITY["pad_factor"],
                    help="flag a speech span whose output/source length ratio exceeds the "
                         "file's median ratio by this factor (padding check)")
    ap.add_argument("--drop-factor", type=float, default=FIDELITY["drop_factor"],
                    help="flag a speech span whose output/source length ratio falls below "
                         "this fraction of the file's median ratio (dropped-content check)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="only print errors and the summary")
    args = ap.parse_args()

    lang = args.lang.lower()
    try:
        profiles = load_language_profiles(args.lang_config)
    except ValueError as exc:
        ap.error(str(exc))
    profile, profile_code = language_profile_resolution(lang, profiles)
    cfg = {
        "lang": lang,
        "profile_code": profile_code,
        "max_cps": args.max_cps if args.max_cps else profile["max_cps"],
        "max_width": args.max_width if args.max_width else profile["max_width"],
        "counting": profile["counting"],
        "final_punct": profile["final_punctuation"] == "none",
        "ban_exclamation": profile.get("ban_exclamation", False),
        "spacing": profile["spacing"],
        "strict": args.strict,
        "min_duration": args.min_duration,
        "max_duration": args.max_duration,
        "max_lines": args.max_lines,
        "pause_gap": args.pause_gap,
        "min_split_piece": DEFAULTS["min_split_piece"],
        "min_span_cost": FIDELITY["min_span_cost"],
        "min_spans": FIDELITY["min_spans"],
        "pad_factor": args.pad_factor,
        "drop_factor": args.drop_factor,
        "max_reports": FIDELITY["max_reports"],
    }
    fmt = detect_format(args.output, args.format)
    src_fmt = detect_format(args.source, args.format) if args.source else None
    blocks, errors, warnings, notes = check(args.output, args.source, fmt, src_fmt, cfg)
    if profile_code == "default" and lang not in ("default", ""):
        notes.append("language %s is not configured; used the explicit default profile" % lang)
    elif profile_code != lang:
        notes.append("language %s uses the %s profile" % (lang, profile_code))

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
