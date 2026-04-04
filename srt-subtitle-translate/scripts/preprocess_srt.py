#!/usr/bin/env python3
"""Normalize subtitle text in SRT-like timed blocks and optionally re-segment local sentence boundaries."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import sys


TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s-->\s\d{2}:\d{2}:\d{2},\d{3}"
    r"(?:\s+.*)?$"
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+(?=(?:[\"'”’\)\]]*)[A-Z0-9\u4e00-\u9fff])")
TERMINAL_PUNCTUATION = ".!?。！？"
CONTINUATION_WORDS = {
    "a", "an", "the", "this", "that", "these", "those",
    "my", "your", "our", "their", "his", "her", "its",
    "have", "has", "had", "having",
    "to", "into", "onto", "for", "of", "with", "from",
    "and", "or", "but", "if", "when", "because", "than",
    "then", "should", "could", "would", "can", "will",
}
CONNECTOR_WORDS = {
    "and", "but", "or", "so", "then", "because", "if", "when", "while", "as",
}
SOFT_CONTINUATION_STARTS = (
    "kind of",
    "sort of",
    "similar to",
    "around",
    "about",
    "approximately",
)
PROTECTED_SPLIT_PAIRS = (
    ("as well", "as"),
    ("kind", "of"),
    ("sort", "of"),
)
PREFERRED_BREAK_STARTS = {
    "and", "but", "so", "because", "then", "which", "where", "when", "while",
    "once", "if", "as", "though", "although", "after", "before", "meanwhile",
}
SECONDARY_BREAK_STARTS = {
    "to", "into", "onto", "from", "with", "without", "over", "under", "through",
    "around", "across", "inside", "outside",
}
WEAK_BREAK_STARTS = {
    "a", "an", "the", "this", "that", "these", "those",
    "my", "your", "our", "their", "his", "her", "its",
    "it", "them", "him", "her", "us", "me",
    "can", "will", "would", "could", "should", "have", "has", "had",
    "all", "here", "there", "model", "emitter", "click",
    "to",
    "of", "in", "on", "at", "with", "for", "from", "into", "onto", "over", "under", "around", "through",
}
DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those",
    "my", "your", "our", "their", "his", "her", "its",
}
PREPOSITIONS = {
    "in", "on", "at", "to", "into", "onto", "from", "with", "without", "over",
    "under", "through", "around", "across", "inside", "outside", "for", "of",
}
COMPOUND_HEAD_WORDS = {
    "model", "setup", "shape", "geometry", "mode", "tool", "tools", "selection",
    "condition", "field", "material", "group", "emitter", "opener", "object",
    "objects", "particle", "particles", "cloner", "effector", "sphere", "spheres",
    "light", "mesh", "origin", "point", "axis", "center",
}
LOCATION_ADVERBS = {"here", "there"}
DIRECTIONAL_MODIFIERS = {"right", "left", "double"}
COMMAND_HEADS = {"click", "drag", "drop", "tap"}
COPULAR_WORDS = {"is", "are", "was", "were"}
COMPLEMENT_STARTERS = {
    "we", "you", "i", "they", "it", "he", "she",
    "what", "how", "why", "where", "when", "who",
    "that", "this", "to",
}
DISCOURSE_FRAGMENT_WORDS = {
    "maybe", "okay", "ok", "like", "well", "right", "alright", "anyway",
    "firstly", "secondly", "thirdly", "first", "next", "now",
}
ORPHAN_LEAD_PATTERNS = (
    re.compile(r"(?i)^(?:what|all|that)\b.+\b(?:is|are|was|were)$"),
    re.compile(r"(?i)^i\s+(?:really\s+)?like$"),
    re.compile(r"(?i)^for\b.+$"),
    re.compile(r"(?i)^to\b.+$"),
)
OBJECT_TAKING_VERBS = {
    "adjust", "position", "move", "rotate", "select", "change", "bring", "make",
    "keep", "place", "drop", "turn", "set", "put", "head", "open", "close",
    "add", "remove", "drag", "push", "pull", "raise", "lower", "tip",
}
WEAK_ENDING_RE = re.compile(
    r"(?i)\b(?:and\s+|but\s+|so\s+)?(?:we|i|you|they|it)\s+(?:can|will|would|could|should|need|want|just)$"
)
MAX_CROSS_BLOCK_GAP_MS = 2500
MIN_REBUILT_DURATION_MS = 900
CLAUSE_BREAK_RE = re.compile(
    r"(?i)(?<=,)\s+|(?<=;)\s+|(?<=:)\s+|\s+(?=but\b|because\b|so\b|then\b|while\b|where\b|when\b|if\b|as\b)"
)


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


def split_sentences(text: str) -> list[str]:
    prepared = normalize_source_text(text)
    prepared = re.sub(r"\s*([.!?。！？])\s*", r"\1 ", prepared).strip()
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(prepared) if part.strip()]
    if not parts:
        return [text] if text else []
    return [collapse_spaces(part) for part in parts]


def last_word(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return words[-1] if words else ""


def first_word(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    return words[0] if words else ""


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def last_alpha_word(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return words[-1] if words else ""


def strip_terminal_punctuation(text: str) -> str:
    return text.rstrip(TERMINAL_PUNCTUATION + "\"'”’)]").strip()


def is_incomplete_chunk(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    if compact[-1] not in TERMINAL_PUNCTUATION:
        return True
    stripped = compact.rstrip(TERMINAL_PUNCTUATION + "\"'”’)]")
    tail_word = last_word(stripped)
    if tail_word in CONTINUATION_WORDS or tail_word in COPULAR_WORDS:
        return True
    if tail_word in {"maybe", "like", "okay", "ok", "well", "right", "alright"}:
        return True
    lowered = stripped.lower()
    if any(pattern.fullmatch(lowered) for pattern in ORPHAN_LEAD_PATTERNS):
        return True
    return False


def is_connector_fragment(text: str) -> bool:
    compact = strip_terminal_punctuation(text).lower()
    return compact in CONNECTOR_WORDS


def is_singleton_fragment(text: str) -> bool:
    compact = strip_terminal_punctuation(text)
    if not compact:
        return False
    if is_connector_fragment(compact):
        return False
    if word_count(compact) != 1:
        return False
    return len(compact) <= 14


def is_orphan_lead_fragment(text: str) -> bool:
    compact = strip_terminal_punctuation(text)
    if not compact:
        return False

    lowered = compact.lower()
    words = re.findall(r"[A-Za-z0-9']+", lowered)
    if not words:
        return False

    if compact.endswith("..."):
        return True
    if len(words) <= 2 and words[0] in DISCOURSE_FRAGMENT_WORDS:
        return True
    if len(words) <= 3 and words[0] in CONNECTOR_WORDS:
        return True
    if len(words) <= 5 and words[0] in {"for", "to"}:
        return True
    return any(pattern.fullmatch(lowered) for pattern in ORPHAN_LEAD_PATTERNS)


def starts_soft_continuation(text: str) -> bool:
    compact = strip_terminal_punctuation(text).lower()
    return any(compact.startswith(prefix) for prefix in SOFT_CONTINUATION_STARTS)


def is_numeric_tail(text: str) -> bool:
    compact = strip_terminal_punctuation(text)
    if not compact:
        return False
    return bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", compact))


def is_parameter_value_fragment(text: str) -> bool:
    compact = strip_terminal_punctuation(text)
    if not compact:
        return False
    if is_numeric_tail(compact):
        return True
    return bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:%|x|×|°)?", compact))


def lowercase_continuation(text: str) -> str:
    if re.match(r"^I(?:\b|')", text):
        return text
    if re.match(r"^[A-Z][a-z]", text):
        return text[0].lower() + text[1:]
    return text


def has_terminal_punctuation(text: str) -> bool:
    compact = text.rstrip()
    return bool(compact) and compact[-1] in TERMINAL_PUNCTUATION


def merge_chunks(left: str, right: str, *, lowercase_right: bool = True) -> str:
    left_compact = strip_terminal_punctuation(left)
    if left_compact:
        left = left_compact
    if is_numeric_tail(right):
        continuation = strip_terminal_punctuation(right)
    elif lowercase_right:
        continuation = lowercase_continuation(strip_terminal_punctuation(right))
    else:
        continuation = strip_terminal_punctuation(right)
    merged = collapse_spaces(f"{left} {continuation}")
    if has_terminal_punctuation(right) and not is_connector_fragment(right):
        return f"{merged}{right.rstrip()[-1]}"
    return merged


def block_gap_ms(left_timestamp: str, right_timestamp: str) -> int:
    _, left_end = parse_timestamp_range(left_timestamp)
    right_start, _ = parse_timestamp_range(right_timestamp)
    return max(0, right_start - left_end)


def redistribute_timestamps(
    texts: list[str],
    start_ms: int,
    end_ms: int,
) -> list[str]:
    if len(texts) == 1:
        return [make_timestamp(start_ms, end_ms)]

    total_duration = max(1, end_ms - start_ms)
    weights = [max(1, len(text)) for text in texts]
    total_weight = sum(weights)
    boundaries = [start_ms]
    accumulated = start_ms

    for weight in weights[:-1]:
        slice_duration = max(1, round(total_duration * (weight / total_weight)))
        accumulated += slice_duration
        boundaries.append(accumulated)

    boundaries.append(end_ms)
    boundaries = sorted(boundaries)
    boundaries[0] = start_ms
    boundaries[-1] = end_ms

    timestamps: list[str] = []
    for index, text in enumerate(texts):
        segment_start = boundaries[index]
        segment_end = boundaries[index + 1]
        if segment_end <= segment_start:
            segment_end = segment_start + 1
            if index == len(texts) - 1:
                segment_end = end_ms
        timestamps.append(make_timestamp(segment_start, segment_end))
    timestamps[-1] = make_timestamp(parse_timestamp_range(timestamps[-1])[0], end_ms)
    return timestamps


def rebalance_unreadable_parts(
    texts: list[str],
    start_ms: int,
    end_ms: int,
) -> list[str]:
    parts = [collapse_spaces(text) for text in texts if collapse_spaces(text)]
    if len(parts) <= 1:
        return parts

    while len(parts) > 1:
        timestamps = redistribute_timestamps(parts, start_ms, end_ms)
        durations = [
            parse_timestamp_range(timestamp)[1] - parse_timestamp_range(timestamp)[0]
            for timestamp in timestamps
        ]
        bad_index = None
        for index, (part, duration) in enumerate(zip(parts, durations)):
            if duration >= MIN_REBUILT_DURATION_MS and not (
                is_parameter_value_fragment(part) and duration < 1500
            ):
                continue
            bad_index = index
            break

        if bad_index is None:
            break

        if bad_index == 0:
            merge_index = 1
            parts[merge_index] = collapse_spaces(f"{parts[bad_index]} {parts[merge_index]}")
            del parts[bad_index]
            continue

        if is_parameter_value_fragment(parts[bad_index]):
            parts[bad_index - 1] = collapse_spaces(f"{parts[bad_index - 1]} {parts[bad_index]}")
            del parts[bad_index]
            continue

        if bad_index == len(parts) - 1:
            parts[bad_index - 1] = collapse_spaces(f"{parts[bad_index - 1]} {parts[bad_index]}")
            parts.pop()
            continue

        if durations[bad_index - 1] >= durations[bad_index + 1]:
            parts[bad_index - 1] = collapse_spaces(f"{parts[bad_index - 1]} {parts[bad_index]}")
            del parts[bad_index]
        else:
            parts[bad_index + 1] = collapse_spaces(f"{parts[bad_index]} {parts[bad_index + 1]}")
            del parts[bad_index]

    return parts


def split_long_text(text: str, max_chars: int, max_parts: int) -> list[str] | None:
    text = collapse_spaces(text)
    if not text or len(text) <= max_chars or max_parts <= 1:
        return None

    sentence_parts = split_sentences(text)
    if len(sentence_parts) > 1:
        merged_sentence_parts: list[str] = []
        remaining_slots = max_parts
        remaining_sentences = len(sentence_parts)
        for sentence in sentence_parts:
            max_for_sentence = max(1, remaining_slots - (remaining_sentences - 1))
            if len(sentence) <= max_chars or max_for_sentence <= 1:
                parts = [sentence]
            else:
                parts = split_long_text(sentence, max_chars, max_for_sentence) or [sentence]
            merged_sentence_parts.extend(parts)
            remaining_slots -= len(parts)
            remaining_sentences -= 1
        if 1 < len(merged_sentence_parts) <= max_parts:
            return merged_sentence_parts

    words = list(re.finditer(r"\S+", text))
    if len(words) <= 3:
        return None

    boundaries = [0]
    for match in words[:-1]:
        boundaries.append(match.end())
    boundaries.append(len(text))

    def boundary_penalty(position: int) -> float:
        if position <= 0 or position >= len(text):
            return 0.0
        left = text[:position].rstrip()
        right = text[position:].lstrip()
        left_tail = left[-12:].lower()
        right_head = right[:24].lower()
        left_words = re.findall(r"[A-Za-z']+", left.lower())
        next_word_match = re.match(r"[A-Za-z']+", right)
        next_word = next_word_match.group(0).lower() if next_word_match else ""

        if any(left_tail.endswith(a) and next_word == b for a, b in PROTECTED_SPLIT_PAIRS):
            return 120.0
        if left.endswith(tuple(TERMINAL_PUNCTUATION)):
            return -36.0
        if left.endswith(",") and re.search(r"(?i)\bwhen we\b", left):
            return -28.0
        if left.endswith(",") and re.search(r"(?i)\bit looks like\b", right):
            return -22.0
        if left_words and left_words[-1] in DETERMINERS:
            return 42.0
        if len(left_words) >= 2 and left_words[-2] in PREPOSITIONS and left_words[-1] in DETERMINERS:
            return 56.0
        if len(left_words) >= 2 and left_words[-2] in COPULAR_WORDS and left_words[-1] in COMPLEMENT_STARTERS:
            return 72.0
        if left_words and left_words[-1] in COPULAR_WORDS and next_word in COMPLEMENT_STARTERS:
            return 72.0
        if left_words and left_words[-1] in DIRECTIONAL_MODIFIERS and next_word in COMMAND_HEADS:
            return 64.0
        if left_words and left_words[-1] not in PREPOSITIONS and next_word in COMPOUND_HEAD_WORDS:
            return 32.0
        if left_words and left_words[-1] in COMPOUND_HEAD_WORDS and next_word in LOCATION_ADVERBS:
            return 28.0
        if next_word == "to":
            return 52.0
        if next_word in WEAK_BREAK_STARTS:
            penalty = 42.0 if next_word in {"and", "or", "that", "which", "once", "if", "when", "while", "as"} else 30.0
            if next_word in {"and", "or"} and left_words:
                penalty += 24.0
            if left_words and left_words[-1] in OBJECT_TAKING_VERBS:
                penalty += 18.0
            return penalty
        if right_head.startswith("as well as "):
            return -10.0
        if left.endswith((",", ";", ":")):
            return -24.0
        if next_word in PREFERRED_BREAK_STARTS:
            return -11.0
        if next_word in SECONDARY_BREAK_STARTS:
            if left_words and re.search(r"(ed|ing|up|down|back|out)$", left_words[-1]):
                return 18.0
            return 6.0
        return 0.0

    min_part_chars = max(14, round(max_chars * 0.45))
    soft_max_chars = max_chars + 32
    natural_breaks = 0
    for position in boundaries[1:-1]:
        left = collapse_spaces(text[:position])
        right = collapse_spaces(text[position:])
        if len(left) < min_part_chars or len(right) < min_part_chars:
            continue
        if boundary_penalty(position) <= -8.0:
            natural_breaks += 1

    if natural_breaks <= 0 and len(text) <= max_chars + 28:
        return None

    effective_max_parts = min(max_parts, max(2, min(4, natural_breaks + 1)))
    best_parts: list[str] | None = None
    best_score: float | None = None

    for part_count in range(2, effective_max_parts + 1):
        target = len(text) / part_count
        from math import inf

        dp: list[dict[int, tuple[float, list[int]]]] = [{0: (0.0, [])}]
        for used_parts in range(1, part_count + 1):
            layer: dict[int, tuple[float, list[int]]] = {}
            min_remaining = part_count - used_parts
            for start_idx, (score, chosen) in dp[used_parts - 1].items():
                for end_idx in range(start_idx + 1, len(boundaries) - min_remaining):
                    start = boundaries[start_idx]
                    end = boundaries[end_idx]
                    segment = collapse_spaces(text[start:end])
                    if not segment:
                        continue
                    seg_len = len(segment)
                    if seg_len < min_part_chars and used_parts != part_count:
                        continue
                    if seg_len > soft_max_chars:
                        break

                    penalty = abs(seg_len - target)
                    if seg_len < min_part_chars:
                        penalty += (min_part_chars - seg_len) * 2.5
                    if seg_len > max_chars:
                        penalty += (seg_len - max_chars) * 1.15
                    last_word_in_segment = last_alpha_word(segment)
                    if used_parts != part_count:
                        if last_word_in_segment in DETERMINERS:
                            penalty += 40.0
                        elif last_word_in_segment in {"and", "but", "or", "so", "to", "of", "in", "on", "at", "once", "if", "when", "while", "that", "which", "because", "as", "then", "just", "kind", "sort", "all"}:
                            penalty += 52.0 if last_word_in_segment in {"and", "but", "or", "so"} else 30.0
                        elif re.search(r"(ed|ing)$", last_word_in_segment):
                            penalty += 18.0
                    penalty += boundary_penalty(end)
                    if used_parts == part_count and end != len(text):
                        continue

                    total = score + penalty
                    existing = layer.get(end_idx)
                    if existing is None or total < existing[0]:
                        layer[end_idx] = (total, chosen + [end_idx])
            if not layer:
                dp = []
                break
            dp.append(layer)

        if not dp or len(dp) <= part_count or not dp[part_count]:
            continue
        final = dp[part_count].get(len(boundaries) - 1)
        if final is None:
            continue

        score, chosen = final
        score += (part_count - 1) * 18.0
        candidate_parts: list[str] = []
        last_idx = 0
        valid = True
        for boundary_idx in chosen:
            segment = collapse_spaces(text[boundaries[last_idx]:boundaries[boundary_idx]])
            if not segment:
                valid = False
                break
            candidate_parts.append(segment)
            last_idx = boundary_idx
        if not valid or len(candidate_parts) <= 1:
            continue

        if best_score is None or score < best_score:
            best_score = score
            best_parts = candidate_parts

    if not best_parts:
        return None
    parts = best_parts

    pair_fixed = True
    while pair_fixed and len(parts) > 1:
        pair_fixed = False
        for idx in range(len(parts) - 1):
            left = parts[idx].lower().rstrip(",")
            right = parts[idx + 1].lower()
            if any(left.endswith(a) and right.startswith(b) for a, b in PROTECTED_SPLIT_PAIRS):
                parts[idx] = collapse_spaces(f"{parts[idx]} {parts[idx + 1]}")
                del parts[idx + 1]
                pair_fixed = True
                break

    rebalanced = True
    while rebalanced and len(parts) > 1:
        rebalanced = False
        for idx, part in enumerate(parts):
            if len(part) >= min_part_chars and word_count(part) > 2:
                continue
            if idx == 0:
                parts[1] = collapse_spaces(f"{parts[0]} {parts[1]}")
                del parts[0]
            elif idx == len(parts) - 1:
                parts[-2] = collapse_spaces(f"{parts[-2]} {parts[-1]}")
                parts.pop()
            elif len(parts[idx - 1]) <= len(parts[idx + 1]):
                parts[idx - 1] = collapse_spaces(f"{parts[idx - 1]} {parts[idx]}")
                del parts[idx]
            else:
                parts[idx + 1] = collapse_spaces(f"{parts[idx]} {parts[idx + 1]}")
                del parts[idx]
            rebalanced = True
            break

    for idx in range(len(parts) - 1):
        if not WEAK_ENDING_RE.search(parts[idx]):
            continue
        tail_match = re.search(
            r"(?i)\b((?:and\s+|but\s+|so\s+)?(?:we|i|you|they|it)\s+(?:can|will|would|could|should|need|want|just))$",
            parts[idx],
        )
        if not tail_match:
            continue
        left_head = collapse_spaces(parts[idx][:tail_match.start()])
        tail = tail_match.group(1)
        if len(left_head) < min_part_chars:
            continue
        parts[idx] = left_head
        parts[idx + 1] = collapse_spaces(f"{tail} {parts[idx + 1]}")

    if len(parts) > 1 and (word_count(parts[-1]) <= 1 or len(parts[-1]) < 8):
        parts[-2] = collapse_spaces(f"{parts[-2]} {parts[-1]}")
        parts.pop()
    return parts if len(parts) > 1 else None



def split_overlong_blocks(
    blocks: list[tuple[str, str, list[str]]],
    max_chars: int,
) -> list[tuple[str, str, list[str]]]:
    normalized = []
    for cue, timestamp, lines in blocks:
        text_lines = normalize_text_lines(lines, False)
        normalized.append({
            "cue": cue,
            "timestamp": timestamp,
            "text": text_lines[0] if text_lines else "",
        })

    index = 0
    while index < len(normalized):
        text = normalized[index]["text"]
        if not text or len(text) <= max_chars:
            index += 1
            continue

        available = 1
        lookahead = index + 1
        while lookahead < len(normalized) and not normalized[lookahead]["text"]:
            available += 1
            lookahead += 1

        desired_parts = max(2, min(4, max(2, math.ceil(len(text) / max_chars))))
        split_parts = split_long_text(text, max_chars=max_chars, max_parts=max(available, desired_parts))
        if not split_parts:
            index += 1
            continue

        if available <= 1 or len(split_parts) > available:
            start_ms, end_ms = parse_timestamp_range(normalized[index]["timestamp"])
            split_parts = rebalance_unreadable_parts(split_parts, start_ms, end_ms)
            timestamps = redistribute_timestamps(split_parts, start_ms, end_ms)
            replacement = [
                {
                    "cue": normalized[index]["cue"],
                    "timestamp": timestamps[offset],
                    "text": part,
                }
                for offset, part in enumerate(split_parts)
            ]
            normalized[index:lookahead] = replacement
            index += len(replacement)
            continue

        run_end = index + len(split_parts) - 1
        start_ms = parse_timestamp_range(normalized[index]["timestamp"])[0]
        end_ms = parse_timestamp_range(normalized[run_end]["timestamp"])[1]
        split_parts = rebalance_unreadable_parts(split_parts, start_ms, end_ms)
        timestamps = redistribute_timestamps(split_parts, start_ms, end_ms)

        for offset, part in enumerate(split_parts):
            normalized[index + offset]["text"] = part
            normalized[index + offset]["timestamp"] = timestamps[offset]

        for clear_index in range(index + len(split_parts), lookahead):
            normalized[clear_index]["text"] = ""

        index = lookahead

    return [
        (
            item["cue"],
            item["timestamp"],
            [item["text"]] if item["text"] else [],
        )
        for item in normalized
    ]


def resegment_blocks(blocks: list[tuple[str, str, list[str]]]) -> list[tuple[str, str, list[str]]]:
    normalized = []
    for cue, timestamp, lines in blocks:
        text_lines = normalize_text_lines(lines, False)
        text = text_lines[0] if text_lines else ""
        normalized.append({
            "cue": cue,
            "timestamp": timestamp,
            "text": text,
            "chunks": split_sentences(text) if text else [],
        })

    changed = [False] * len(normalized)

    changed_any = True
    while changed_any:
        changed_any = False

        for block_index, item in enumerate(normalized):
            chunk_index = 0
            while chunk_index < len(item["chunks"]) - 1:
                left = item["chunks"][chunk_index]
                right = item["chunks"][chunk_index + 1]
                should_merge = (
                    is_incomplete_chunk(left)
                    or is_connector_fragment(left)
                    or is_orphan_lead_fragment(left)
                    or is_singleton_fragment(right)
                    or is_orphan_lead_fragment(right)
                    or starts_soft_continuation(right)
                    or is_numeric_tail(right)
                )
                if not should_merge:
                    chunk_index += 1
                    continue
                item["chunks"][chunk_index] = merge_chunks(
                    left,
                    right,
                    lowercase_right=not is_connector_fragment(left),
                )
                del item["chunks"][chunk_index + 1]
                changed[block_index] = True
                changed_any = True

        for i in range(1, len(normalized)):
            if not normalized[i]["chunks"]:
                continue
            previous = i - 1
            while previous >= 0 and not normalized[previous]["chunks"]:
                previous -= 1
            if previous < 0:
                continue

            current_first = normalized[i]["chunks"][0]
            if (
                is_singleton_fragment(current_first)
                or is_orphan_lead_fragment(current_first)
                or starts_soft_continuation(current_first)
                or is_numeric_tail(current_first)
            ):
                if block_gap_ms(normalized[previous]["timestamp"], normalized[i]["timestamp"]) > MAX_CROSS_BLOCK_GAP_MS:
                    continue
                normalized[previous]["chunks"][-1] = merge_chunks(
                    normalized[previous]["chunks"][-1],
                    current_first,
                )
                del normalized[i]["chunks"][0]
                changed[previous] = True
                changed[i] = True
                changed_any = True

        for i in range(len(normalized) - 1):
            while normalized[i]["chunks"] and (
                is_incomplete_chunk(normalized[i]["chunks"][-1])
                or is_connector_fragment(normalized[i]["chunks"][-1])
                or is_orphan_lead_fragment(normalized[i]["chunks"][-1])
            ):
                next_index = i + 1
                while next_index < len(normalized) and not normalized[next_index]["chunks"]:
                    next_index += 1
                if next_index >= len(normalized):
                    break
                if block_gap_ms(normalized[i]["timestamp"], normalized[next_index]["timestamp"]) > MAX_CROSS_BLOCK_GAP_MS:
                    break
                normalized[i]["chunks"][-1] = merge_chunks(
                    normalized[i]["chunks"][-1],
                    normalized[next_index]["chunks"][0],
                    lowercase_right=not is_connector_fragment(normalized[i]["chunks"][-1]),
                )
                del normalized[next_index]["chunks"][0]
                changed[i] = True
                changed[next_index] = True
                changed_any = True

    for i in range(len(normalized)):
        chunks = normalized[i]["chunks"]
        if chunks and (word_count(chunks[-1]) <= 2 or is_orphan_lead_fragment(chunks[-1])):
            next_index = i + 1
            while next_index < len(normalized) and not normalized[next_index]["chunks"]:
                next_index += 1
            if next_index >= len(normalized):
                continue
            if block_gap_ms(normalized[i]["timestamp"], normalized[next_index]["timestamp"]) > MAX_CROSS_BLOCK_GAP_MS:
                continue
            current_last = chunks[-1]
            next_first = normalized[next_index]["chunks"][0]
            if is_connector_fragment(current_last) and not is_connector_fragment(next_first):
                normalized[i]["chunks"][-1] = merge_chunks(
                    current_last,
                    next_first,
                    lowercase_right=False,
                )
                del normalized[next_index]["chunks"][0]
                changed[i] = True
                changed[next_index] = True

    for item in normalized:
        item["text"] = collapse_spaces(" ".join(item["chunks"])) if item["chunks"] else ""

    result = []
    index = 0
    while index < len(normalized):
        if not changed[index]:
            text_lines = [normalized[index]["text"]] if normalized[index]["text"] else []
            result.append((normalized[index]["cue"], normalized[index]["timestamp"], text_lines))
            index += 1
            continue

        run_start = index
        run_end = index
        while (
            run_end + 1 < len(normalized)
            and changed[run_end + 1]
            and block_gap_ms(normalized[run_end]["timestamp"], normalized[run_end + 1]["timestamp"]) <= MAX_CROSS_BLOCK_GAP_MS
        ):
            run_end += 1

        start_ms = parse_timestamp_range(normalized[run_start]["timestamp"])[0]
        end_ms = parse_timestamp_range(normalized[run_end]["timestamp"])[1]
        texts = [normalized[i]["text"] for i in range(run_start, run_end + 1)]
        timestamps = redistribute_timestamps(texts, start_ms, end_ms)

        for offset, item_index in enumerate(range(run_start, run_end + 1)):
            text_lines = [normalized[item_index]["text"]] if normalized[item_index]["text"] else []
            result.append((normalized[item_index]["cue"], timestamps[offset], text_lines))

        index = run_end + 1

    return result


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
        description="Normalize subtitle text in SRT-like timed blocks while preserving numbering and timestamps.",
    )
    parser.add_argument("input", help="Path to input subtitle file, such as .srt or .txt")
    parser.add_argument(
        "output",
        nargs="?",
        help="Optional output subtitle path. Defaults to source sibling with -CN suffix.",
    )
    parser.add_argument(
        "--keep-line-breaks",
        action="store_true",
        help="Preserve per-cue line breaks instead of joining text into one line.",
    )
    parser.add_argument(
        "--resegment-sentences",
        action="store_true",
        help="Rebuild sentence boundaries across adjacent cues and redistribute timestamps locally.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=42,
        help="Target maximum characters per source subtitle cue during preprocessing.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}-CN{input_path.suffix}")

    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    content = input_path.read_text(encoding="utf-8-sig")

    try:
        blocks = parse_blocks(content)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.resegment_sentences:
        blocks = resegment_blocks(blocks)
    blocks = split_overlong_blocks(blocks, max_chars=args.max_chars)
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

