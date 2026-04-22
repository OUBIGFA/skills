---
name: srt-subtitle-translate
description: Translate non-Chinese subtitle files into concise, publication-grade Simplified Chinese while preserving cue order and timing structure as faithfully as possible. Use when the assistant needs to translate or polish subtitle files such as `.srt`, `.txt`, `.vtt`, `.ass`, `.ssa`, `.sub`, subtitle blocks, or transcript-like timed captions into Chinese with filler-word cleanup, terminology preservation, symbol normalization, subtitle-safe formatting, and optional local re-segmentation with sequential renumbering.
---

# SRT Subtitle Translate

Translate subtitle content into concise Simplified Chinese while preserving cue order and timing structure as faithfully as possible. This skill is built around one principle: the main language model in the current conversation must own the three critical stages itself.

## Core Principle

The workflow has three mandatory human-in-the-loop stages, all performed by the main model in the current conversation:

1. Semantic segmentation review
2. Translation
3. Review and polish

Local scripts may normalize files, extract term candidates, generate report-only boundary hints, split long files into chunks, validate structure, and merge chunk drafts. Scripts must never replace semantic segmentation decisions, translation, or final review.

## Highest-Priority Rules

- Subtitle translation itself must be performed by the language model running this task.
- Semantic segmentation decisions must be made by the language model based on meaning, not by heuristic scripts.
- Final review and polish must also be performed by the language model in the main conversation before the formal `-CN` deliverable is considered complete.
- Do not search for, probe for, install, call, or switch to any external translator, translation website, translation API, browser translation flow, or third-party translation library.
- Do not pause an executable end-to-end subtitle task for procedural confirmation requests.
- Preserve cue order and timing structure unless source-side segmentation repair is clearly necessary.
- Every in-progress translated file must preserve exactly the same cue numbers, timestamps, cue order, and block count as its paired source file. Only subtitle text may change at translation time.

## Execution Model

- Prefer translation inside the current assistant conversation.
- Prefer one-pass full-file translation when the subtitle corresponds to a short video, especially when the full runtime is within about 30 minutes and the file can be handled safely in one conversation.
- If the subtitle file is larger, split it into sequential chunks and continue in the current main conversation.
- Do not default to parallel subagents for subtitle translation.
- If chunking is used, each chunk translation is only a draft until the merged subtitle has been reviewed and polished against the source by the main conversation.
- Do not treat the lack of a separate translation library as a blocker. The model itself is the translator.

## Hard Constraints

- Do not write intermediate resources, caches, or temporary artifacts into the skill directory itself.
- Do not reframe the task as blocked merely because helper scripts do not translate text.
- Do not execute translator-discovery commands.
- Do not search for existing subtitle artifacts as a substitute for doing the translation now.
- Do not stop at preview slices, sample output, or partial subtitle ranges unless the user explicitly asks for a preview-only run.
- Only interrupt the flow for a concrete blocker such as a missing source file, write failure, or malformed subtitle structure that cannot be safely repaired.

## Workflow

1. Detect whether the input is standard SRT or SRT-like subtitle blocks.
2. If the file extension is generic text such as `.txt`, inspect the content and treat it as subtitles when it follows numbered timed blocks.
3. Read the full subtitle once to identify recurring names, product names, UI labels, abbreviations, and other terms that must stay consistent.
4. If useful, generate a temporary term candidate list with `scripts/extract_subtitle_terms.py`, then refine the actual wording decisions in the current conversation.
5. Normalize whitespace and wrapping with `scripts/preprocess_srt.py` when the source is noisy.
6. Perform a semantic segmentation review in the main conversation. Repair broken cue boundaries only when the source segmentation is clearly unsuitable for translation.
7. If boundary issues are obvious and a quick hint would help, optionally inspect `scripts/detect_orphan_tails.py` or `scripts/detect_clause_rebalance.py` reports. These scripts are report-only helpers, not mandatory workflow stages.
8. Translate the subtitle text in the main conversation.
9. If the file is too large for one stable pass, split it with `scripts/chunk_srt.py split` and translate chunks sequentially in the same main conversation.
10. Validate chunk structure and merge chunk drafts locally.
11. Run a mandatory final review and polish pass in the main conversation against the source subtitle.
12. Write the formal sibling `-CN` file only after that final review and polish pass is complete.
13. Clean intermediate artifacts unless the user explicitly asks to keep them.

## Quick Start

- Use `scripts/preprocess_srt.py` when you need whitespace normalization or line-join cleanup.
- Use `scripts/extract_subtitle_terms.py` when recurring terms need a temporary glossary.
- Use `scripts/detect_orphan_tails.py` or `scripts/detect_clause_rebalance.py` only as optional report-only hints during semantic segmentation review.
- If the subtitle is short, translate the whole file directly after preprocessing and review.
- If the subtitle is large enough that one-pass translation could truncate or drift, use `scripts/chunk_srt.py split` and then translate the generated chunks sequentially in the same main conversation.
- After chunk translation, merge to a draft subtitle first, then complete the final review and polish pass, then write the formal `-CN` result.
- Save the final translated result beside the source subtitle file and append `-CN` before the original extension.
- Example: `demo.srt` -> `demo-CN.srt`
- Example: `demo.txt` -> `demo-CN.txt`
- Read [references/terminology.md](references/terminology.md) only when terminology consistency or formatting policy matters.

## Output Contract

- Output only the translated subtitle blocks.
- Keep cue order identical to the input.
- After preprocessing, treat the resulting subtitle blocks as the canonical translation units for the final Chinese output.
- By default, preserve the preprocessed cue boundaries exactly in the Chinese subtitle. Do not merge, split, or redistribute translated text across adjacent cues during Chinese translation just to improve phrasing.
- Only adjust Chinese word order, compression, and phrasing inside the current cue.
- Do not require rebuilt cue numbers to match the original cue numbers.
- After source-side re-segmentation, renumber cues sequentially from top to bottom in the final output.
- Preserve timestamps exactly unless preprocessing is explicitly used to repair broken segmentation.
- Do not reorder or skip subtitle blocks.
- In chunked workflows, each translated chunk must preserve exactly the same subtitle blocks as its source chunk: same cue numbers, same timestamps, same cue order, and same block count.
- Names, terminology, and first-chosen translations must remain consistent across the entire file.
- Do not add explanations, notes, comments, or reasoning.
- Do not emit citation markers such as `[cite]`, `[]`, or Markdown quotes.
- Do not end translated subtitle lines with Chinese sentence-final punctuation such as `。`, `！`, `？`, or `；` unless the source format absolutely requires it.
- Minimize internal Chinese punctuation too. Use commas or pauses only when they materially improve subtitle readability or prevent ambiguity.
- If saving to a file, write the translated subtitle beside the source file and append `-CN` before the original extension.

## Translation Rules

### Clean for subtitles

- Remove filler words, hesitation sounds, and low-information fragments when they do not affect meaning.
- Rewrite broken speech into compact Chinese instead of translating every disfluency literally.
- Keep short acknowledgements only when they carry real semantic value.
- Preserve technical terms, product names, and important English terms when forced translation would reduce accuracy.
- Normalize symbols, units, and mixed Chinese/English spacing before returning the final subtitle text.

### Repair segmentation when needed

- This section applies to source-side preprocessing, not to the final Chinese translation pass.
- Once preprocessing is finished, do not perform a second Chinese-side re-segmentation pass unless the user explicitly asks for rebuilt Chinese subtitle timing.
- Apply aggressive local sentence repair mainly to English source subtitles. For non-English subtitles, repair boundaries only when the intended sentence boundary is unambiguous.
- Keep re-segmentation local. Adjust only the neighboring cues needed to fix reading flow.
- Prefer semantic completeness over arbitrary source cuts.
- Redistribute time in proportion to segment length unless the speech rhythm clearly suggests another split.
- Avoid creating unreadably short flashes.
- Protect noun phrases, prepositional phrases, phrasal verbs, subject-plus-modal units, and compact UI action phrases as complete reading units.
- If a single cue is too long for subtitle reading, split it at the least awkward semantic hinge rather than preserving one oversized cue.
- When a short interjection such as `Okay`, `Let's see`, or `I guess` does not materially affect the instruction, compress or omit it in Chinese rather than preserving conversational filler.

## Tool Notes

- `preprocess_srt.py` is restricted to whitespace and formatting normalization. It does not resegment cues or redistribute timestamps.
- `detect_orphan_tails.py` and `detect_clause_rebalance.py` are report-only scanners. They never rewrite subtitle files.
- `chunk_srt.py split` creates source chunks and `manifest.json` for sequential chunk translation.
- `chunk_srt.py merge` validates that translated chunks preserve source structure, then merges them into one subtitle draft.
- `subtitle_pipeline.py prepare` normalizes input, extracts term candidates, optionally generates boundary-hint reports, decides whether direct translation or sequential chunking is preferred, and writes pipeline metadata.
- `subtitle_pipeline.py set-stage` persists the current workflow stage after main-conversation work such as translation or review/polish.
- `subtitle_pipeline.py finalize` merges chunk drafts. Without `--reviewed`, it writes a draft subtitle only. With `--reviewed`, it writes the formal final output and can clean intermediates.
