---
name: srt-subtitle-translator
description: Translate and re-segment timed subtitle files in SRT, WebVTT, or ASS/SSA format while preserving timing, markup, and format-specific structure. Use for subtitle translation, bilingual subtitles, or translation-aware segmentation repair. Do not use for timing-only inspection, extraction, muxing/burning, or format conversion without translation.
metadata:
  short-description: Translate and repair timed subtitle files
---

# Subtitle Translator

Translate subtitle text faithfully and concisely, then place the target-language
boundaries where they read naturally. The target language is the one requested by the
user; Simplified Chinese is the default only when no target is given.

## Core contract

- Fidelity comes first: preserve every claim, operation, value, name, warning, causal
  link, negation, and uncertainty marker. Remove filler, not payload.
- Keep the speaker's register. Do not add subjects, connectives, explanations,
  politeness, necessity, or conclusions that were not spoken.
- Work in this order: repair clear ASR segmentation defects, translate the complete
  sentence, then divide the translation at target-language thought boundaries.
- Never cross a real pause. A gap in a subtitle file is only a pause proxy; without
  audio, do not claim that it proves an audible pause.
- Keep the source format. Convert only when explicitly requested, and state what the
  conversion loses.
- Never use translation APIs, browser translation, online translators, MT plugins, or
  local machine-translation software. Local tools may inspect, assemble, and validate
  files.

## When this skill applies

Use it when the user asks to:

- translate SRT, VTT, ASS, or SSA subtitles or captions;
- create bilingual subtitles;
- repair ASR segmentation as part of translation or as a requested subtitle edit;
- clean up auto-generated subtitle text while preserving its meaning and timing.

Do not translate merely because a subtitle file is attached. For timing-only audits,
text extraction, subtitle muxing or burning, or format conversion without translation,
use the task-specific workflow instead. A plain transcript with no timestamps keeps its
paragraph shape; no timeline work is possible.

## Segmentation

Use `repair → translate → divide`, never translate each ASR block in isolation.

- Merge only a specific defect: an orphan tail, stranded connector, split term,
  dependent opening, trailing modifier, or filler-only flash block.
- Keep a source boundary when both sides are complete and the target translation also
  has a natural seam. Topic continuity alone is not a merge reason.
- Within a continuous speech span, a translated sentence may stay in one block or be
  split at a target-language phrase boundary. Keep the span's first and last times;
  distribute new interior times across the spoken material.
- Do not create a new gap. A small source gap may be preserved, but output gaps must
  correspond to an existing source gap or the checker will reject them.
- Every output piece must be a self-contained target-language phrase. Never strand a
  preposition, connector, governing verb, classifier, modifier, or technical term.

Read [segmentation.md](references/segmentation.md) before auditing or placing a
boundary. It contains the defect taxonomy and target-language seam tests.

## Translation style

Use the shortest natural wording that still carries the source meaning. Read every
finished batch once for padding and once for naturalness. Build a glossary from the
whole file before translating, then keep one rendering per concept unless context
clearly changes the sense.

- Keep UI labels, menu paths, software names, acronyms, file names, object names, and
  text visibly typed on screen searchable and faithful to the source.
- Repair an obvious ASR mishearing from context; if the meaning cannot be recovered,
  translate the available text readably and flag the uncertainty.
- Remove hesitation and filler only when they carry no meaning. Keep real UI words such
  as `OK`, meaningful questions, and speaker labels.
- Use Arabic numerals and standard unit symbols when they are settings or values.

Read [style-common.md](references/style-common.md) for all targets. Read
[style-zh.md](references/style-zh.md) in addition for Chinese. For 3D, motion graphics,
or VFX into Chinese, read [glossary-3d-zh.md](references/glossary-3d-zh.md); it is a
context-sensitive default table, not a find-and-replace list.

## Language configuration

Reading speed, character counting, sentence-final punctuation, and scan width come from
`config/language_profiles.json`. The shipped profiles cover `zh`, `zh-hant`, `ja`,
`ko`, `en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `ar`, `he`, `th`, `vi`, `id`, and `tr`.
Regional codes such as `en-US` use their base-language profile. An unknown code uses the
explicit `default` profile and must be mentioned in the report.

The default Chinese house style uses one half-width space between Chinese and Latin
text, no final full stop, and no exclamation marks. These are style settings, not a
universal rule for every target language; follow the selected profile and any explicit
platform guide.

## Formats and protected content

Read [formats.md](references/formats.md) before handling VTT or ASS/SSA.

- SRT: preserve timestamps and formatting tags; renumber sequentially when boundaries
  change.
- VTT: preserve the `WEBVTT` header, metadata, NOTE/STYLE/REGION blocks, cue IDs,
  settings, escapes, and inline tags. When legal merging combines settings, keep the
  first cue's settings and report the decision.
- ASS/SSA: modify only the Text field of Dialogue events. Preserve sections, styles,
  field order, event type, layer, style, margins, effects, override tags, and existing
  `\N`/`\n` breaks. Do not merge a sign/effect event with dialogue.
- Formatting tags and protected markers must remain balanced and present with the same
  inventory. Bilingual and multi-speaker blocks may use two lines only when requested;
  validate those files with `--max-lines 2`.

## Workflow

1. Read the complete source file and identify its domain, register, recurring terms,
   UI strings, likely ASR errors, and target language.
2. Read the references required by the format, language, domain, or warning being
   handled. Do not load unrelated references.
3. Audit source boundaries and pause proxies, then repair only nameable defects.
4. Translate sentence by sentence, without adding words to bridge repaired seams.
5. Re-divide long translations at natural target-language thought boundaries. Never use
   a character count as the cutting rule.
6. Write UTF-8 output next to the source. For files over about 60 blocks, use
   `scripts/assemble_subtitle.py` for numbered parts rather than pasting the result in
   the reply.
7. Validate before replying:

   ```text
   python scripts/check_subtitle.py <output> --source <input> --lang <target>
   ```

   For bilingual or multi-speaker output, add `--max-lines 2`. For a user-requested
   untouched timeline, add `--strict`. Use `--lang-config` only when a project supplies
   a different profile file.

8. Fix every error. Review warnings for reading load, padding, dropped payload, markup,
   structure, and terminology; explain any deliberately retained warning.
9. After validation succeeds, recycle only temporary artifacts created in this task.
   Follow the platform-safe procedure in [edge-cases.md](references/edge-cases.md).

## Strict mode

Strict mode is explicit-user-request only. It requires the same block count, block order,
timestamp lines, SRT indices, VTT identifiers/settings, ASS non-Text fields, protected
markup, and format structure as the source. Only the dialogue wording may change.

Normal mode may merge or split within a continuous source span, but it must preserve
format structure, protected markers, source span coverage, and source pause proxies.

## Delivery

Keep the final reply short: output path, mode and block count before/after, repair
categories, unresolved timing/ASR/terminology issues, checker result, and one clause
confirming that self-created intermediate files were recycled. Do not put explanations,
citations, or translator notes inside subtitle text.

Use `source-zh.srt` for Simplified Chinese, `source-zh-hant.srt` for Traditional
Chinese, `source.en.srt` for English and the analogous language code for other targets.
Use `.bi.` in place of the language code for bilingual output.

## Reference routing

| Reference | Read when |
|---|---|
| `references/segmentation.md` | Every translation or boundary repair |
| `references/style-common.md` | Every translation |
| `references/style-zh.md` | Chinese target |
| `references/language-profiles.md` | Need human-readable profile explanations or custom calibration |
| `references/reading-load.md` | A duration, reading-speed, or scan-width warning needs judgement |
| `references/formats.md` | VTT, ASS, SSA, tags, or explicit conversion |
| `references/glossary-3d-zh.md` | 3D, motion graphics, or VFX into Chinese |
| `references/edge-cases.md` | Long files, encodings, bilingual output, anomalies, or cleanup |
| `scripts/check_subtitle.py` | Always, before replying |
