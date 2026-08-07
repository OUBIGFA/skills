---
name: srt-subtitle-translator
description: Hand-translate non-Chinese SRT subtitles into clean, professional Simplified Chinese with no machine-translation services involved. Preserves the SRT timeline exactly by default; when the user asks to check or fix segmentation, audits every boundary and repairs only genuine ASR breakage — orphan tails, split terms, stranded prepositions, sub-second flash blocks — before translating. Use this skill whenever the user asks to translate subtitles or captions, review or fix subtitle segmentation, merge fragmented ASR blocks, clean up auto-generated captions, produce a Chinese or bilingual subtitle file, or hands over an .srt file with any request at all — even a bare "translate this". Never route subtitle text through third-party translation APIs, browser translation, online translators, or local MT software.
version: 2.1.0
---

# SRT Subtitle Translator

Turn a foreign-language `.srt` — usually machine-transcribed, usually noisy — into a
Simplified Chinese subtitle file a viewer can read at speed without pausing the video.

Three things decide whether the result is good:

- **Timeline integrity.** Timestamps are contracts with the video. Every one in the output
  must come from the input.
- **Reading load.** Each block must be readable in the time it is on screen. Chinese
  carries more meaning per character than English, so a faithful translation is usually
  too long — condensing is part of the job, not a compromise. Reading load is measured in
  seconds, never in a per-line character count.
- **Boundaries.** ASR cuts on pauses and character counts, not on grammar, so it strands
  articles, prepositions, and single trailing words. Those cuts are defects; the natural
  breaks a speaker actually made are not. Your own breaks must be decided by phrasing
  alone — one block, one line, no wrapping.

## Manual translation only

Translate every line yourself, using context and domain knowledge. Do not call translation
APIs, online translators, browser translation, MT plugins, or local translation software,
and do not write scripts that call them. If asked to use one, say that this skill
translates by hand and continue manually unless the user changes the requirement.

Local tooling is fine for everything that is not translation: reading files, counting
blocks, validating structure, comparing timestamps, formatting output.

## Two modes — pick one before you start

**Structure-preserving (default).** Same indices, same timestamps, same block count, same
order. Translate each block in place. Use this whenever the user only asked for a
translation. Re-segmenting uninvited destroys sync with anything the user has already cut
or burned in.

**Re-segmentation.** Boundaries may be repaired. Triggered by an explicit request (merge
fragments, fix orphan words, re-split) *and* by a conditional one — "先检查，需要就合并",
"看看要不要重新断句" — which authorizes an audit and whatever minimum repairs it finds. It
does not authorize broad merging. Announce the mode decision briefly; do not ask again.

Before repairing boundaries, read `references/segmentation.md`.

## Workflow

1. **Read the whole file first.** Not the first 50 blocks — the whole thing. You are
   looking for the domain, the speaker's habits, recurring UI labels and terms, and
   passages where ASR clearly misheard something. Decide the glossary now, before any line
   is translated; consistency across 300 blocks is impossible to retrofit.

2. **Decide the mode**, and if re-segmentation is authorized, audit every boundary in the
   source language before translating. Classifying boundaries after translation does not
   work — fluent Chinese can paper over a break that still splits the thought in time.

3. **Translate in passes over contiguous ranges.** Keep each block's meaning inside its own
   time window. When one sentence spans several blocks, translate the sentence whole, then
   distribute it as natural Chinese phrases in time order — each block must read on its
   own, none may be left empty, and the whole sentence must not be dumped into one block.

4. **Write the output**, then **verify it mechanically**:

   ```bash
   python <skill>/scripts/check_srt.py <output.zh.srt> --source <input.srt>
   ```

   Errors mean the file is broken — invented timestamps, dropped text, overlap, bad
   numbering — and must be fixed before you reply. Warnings are reading-load and style
   problems; fix them or explain why they stand.

5. **Report briefly**: file path, mode, what was repaired, what needs a human eye. Not the
   subtitle text itself.

## Delivery

Under ~60 blocks: inline in one `srt` code block is fine.

Above that: **write a file**, `source.srt` → `source.zh.srt`, UTF-8, in the source's
directory. A 300-block file pasted into a reply risks silent truncation, and a subtitle
that stops at block 240 with no warning is worse than no subtitle. For long files, build
parts in a temp directory and concatenate — details and the encoding, tag, and bilingual
rules are in `references/edge-cases.md`.

Never mix an explanation into the SRT file. Never emit citation markers, translator notes,
or commentary inside subtitle text.

## Reading-load anchors

Reading load is a function of **time**, not of line width. These are the Netflix Timed Text
Style Guide timing values for Simplified Chinese. Treat them as calibration, not as a
scoring rubric: a block slightly over is fine if the alternative is a worse break, and
being under is normal.

| Parameter | Value |
|---|---|
| Lines per block | 1 — always |
| Reading speed | 9 chars/second (adult), 7 (children's) |
| Minimum duration | 20 frames ≈ 0.83 s |
| Maximum duration | 7 s |
| Minimum gap between blocks | 2 frames |

There is deliberately **no characters-per-line limit**. A character budget cannot tell a
natural phrase from an awkward one, and enforcing it produces exactly the two failures this
skill exists to prevent: text wrapped mid-phrase, and meaning deleted to hit a count.

What the timing values mean in practice: a 2-second block holds about 18 characters, not
30. When the Chinese runs long, condense — drop filler, use symbols and numerals, prefer
the shorter synonym. Cramming is a translation failure, not a timing problem, and in
structure-preserving mode condensing is the *only* lever you have. But never condense past
the meaning: if the choice is between a slightly dense block and a mangled sentence, keep
the sentence.

`scripts/check_srt.py` measures all of this. Its character cost counts a Chinese character
as 1 and a Latin letter or digit as 0.5, and ignores punctuation.

## One block, one line

Every block is a single line of text. Do not wrap, do not split a block across two lines,
and never let a character count decide where text breaks.

When a block feels too long, the answer is always one of:

1. **Condense** the Chinese — this is the default fix,
2. **Redistribute** wording across the neighbouring blocks (source language, sound
   boundaries only), or
3. In re-segmentation mode, **re-audit the boundary** itself.

Never: insert a line break, or delete meaningful words to reach a target length.

Two exceptions, both structural rather than cosmetic: bilingual output (Chinese line,
source line) and multi-speaker blocks where each dash-prefixed speaker needs its own line.
Both are covered in `references/edge-cases.md`.

## Structural rules

Both modes:

- Every timestamp in the output already exists in the input — never invent, shift, round,
  or interpolate a time point
- All source content appears exactly once, in time order; no block is empty
- One line of text per block; no wrapping (see the exceptions above)
- Blank line between blocks; UTF-8; no BOM required but harmless

Structure-preserving mode additionally:

- Indices and timestamp lines are byte-for-byte unchanged
- No merging, splitting, reordering, adding, or dropping blocks
- A garbled or absurdly short block still keeps its index and gets the best readable
  translation available

Re-segmentation mode additionally:

- A merged block spans the first block's start and the last block's end; nothing else moves
- Renumber sequentially from 1
- Merge the smallest group that fixes a specific, nameable defect

## Segmentation in one paragraph

Judge each boundary on two questions, in the source language: does the first block end on a
complete phrase or clause, and can the second block be understood without borrowing a noun,
verb, or object from the first? Both yes → keep it, even if the sentence continues across
it. Either no → merge the smallest adjacent group that repairs it. "Same sentence", "same
topic", and "the merged block would still be readable" are not reasons to merge; a large
drop in block count is a warning sign, not a goal. Character counts are never a reason to
merge or split anything — every boundary decision is a grammar and phrasing decision. Full
taxonomy and worked examples: `references/segmentation.md`.

## Style in one paragraph

Strip filler and hesitation — they cost characters and carry nothing. Use symbols and
Arabic numerals (`-50`, `360°`, `20%`, `10×10`, `3cm`). One half-width space between
Chinese and Latin text or numerals; none between a number and its unit. Keep software
names, UI labels, and acronyms in English unless a stable Chinese term is more familiar.
No sentence-final punctuation at the end of a subtitle line — the cut in time already ends
the thought — and no ellipses or dashes to mark a sentence continuing into the next block.
Repair obvious ASR mishearings from context rather than translating the error. Details,
glossary practice, and a worked domain example: `references/style.md`.

## Files in this skill

| Path | Read it when |
|---|---|
| `references/segmentation.md` | Re-segmentation is authorized — before touching any boundary |
| `references/style.md` | Any translation task; contains noise, symbol, unit, typography, terminology, and ASR-repair rules |
| `references/edge-cases.md` | Long files, odd encodings, tags and speaker labels, bilingual output, timing anomalies, what to report |
| `scripts/check_srt.py` | Always, before replying |

## Optional: streaming-platform punctuation

Netflix's Simplified Chinese guide drops commas and full stops entirely, using a single
space in their place, requires `⋯` (U+2026) for ellipses, forbids italics, and uses
`《》` for titles. If the user is delivering to a streaming platform or asks for
platform-compliant subtitles, follow that convention and say you switched. Otherwise keep
in-line full-width punctuation, which reads more naturally for tutorial and web video.
