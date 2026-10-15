---
name: srt-subtitle-translator
description: Use when translating SRT, VTT, ASS, or SSA subtitles, repairing subtitle segmentation during translation, or cleaning ASR captions while preserving timing and meaning.
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
- Apply the ASD-STE100-inspired controlled-expression pass: first preserve the
  information payload (保留信息载荷), then remove zero-information filler (删去无意义填充词).
  Use short, direct clauses and one term per concept, but do not
  force English wording rules onto another target language or change the speaker's
  register.
- Keep the speaker's register. Do not add subjects, connectives, explanations,
  politeness, necessity, or conclusions that were not spoken.
- Follow simultaneous-interpreting unfolding order (同声传译式展开语序): viewers read
  subtitles in real time while hearing the speech. Where multiple natural renderings exist,
  choose the one whose clausal sequence matches the spoken flow. Never invert or move a
  trailing reason, condition, or afterthought to the front merely to sound like written
  prose, which causes viewers to read the second half before hearing it.
- Deliver exactly one final rendering per sentence: subtitles are broadcast-ready lines,
  not drafts. Never emit slash-separated alternatives (e.g. `微调/蒸馏` or `选项A / 选项B`)
  or bracketed variant notes. A slash is allowed only when the source identifier literally
  contains one (e.g. `/compact`, URLs, or fraction values).
- Respect the division of ASR repair: repair acoustic mishearings (homophones, mangled
  domain terms, broken word boundaries) and restore punctuation boundaries. Do not rewrite
  spoken grammar, reorder clauses, delete words on the timeline, or cut on dangling
  prepositions/connectors (`because.`, `of.`, `当。`, `和。`).
- Work in this order: repair clear ASR segmentation defects, translate the complete
  sentence, then divide the translation at target-language thought boundaries.
- Do not cross a real pause without a nameable reason. A gap in a subtitle file is
  only a pause proxy (often just a breath pause); without audio, do not claim that it proves
  an audible pause or the end of a syntactic thought. Merging across one is the translator's
  judgement call: keep the merge only when it fixes a specific defect, and report every
  crossed gap in the delivery reply.
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

- Audit source ASR seams carefully: acoustic pauses often reflect physiological breaths,
  not syntactic closures. Never sever a unit after a dangling connector, preposition, or
  governing verb.
- Merge only a specific defect: an orphan tail, stranded connector, split term,
  dependent opening, trailing modifier, or filler-only flash block. A defect that
  straddles a source gap may still be merged across it — the checker will flag
  the crossing as a warning; give it a nameable reason in the delivery reply.
- Keep a source boundary when both sides are complete and the target translation also
  has a natural seam. Topic continuity alone is not a merge reason.
- Evaluate width with line-level Display Units (DU): full-width CJK characters cost
  1.0 DU, Latin letters and digits cost 0.5 DU. Respect the soft scan-comfort zone
  (18–25 DU for Chinese) and hard display budget (~30–32 DU). When a translated sentence
  exceeds the hard budget, plan balanced pieces (`k ≥ 2`) at natural target-language
  thought seams (`¦`), distributing interior times across the spoken span.
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

- Keep clause unfolding sequence synchronized with the spoken audio (simultaneous
  interpreting rule): unfolding order outranks written prose conventions.
- Manage terminology with strict tiering:
  - **LOCKED (刚性锁定)**: User-specified renderings, explicit glossary entries, CLI
    commands/flags, product/model names, and code identifiers. These are mandatory
    requirements: reproduce character-for-character with zero alteration of spelling,
    case, or spacing.
  - **preferred (柔性偏好)**: Domain consistency defaults. Follow throughout the file
    for conceptual consistency, but allow context-sensitive flexibility when the
    syntax or physical UI context genuinely demands it.
- Emit exactly one screen-ready rendering per sentence. Strictly avoid slash alternatives
  (`A / B`) or parenthetical variants.
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
Read [asd-ste100-subtitles.md](references/asd-ste100-subtitles.md) for every translation
of technical or instructional speech, or whenever the user asks for concise, controlled,
accurate, or filler-free subtitles. Run its information pass before its economy pass.

## Language configuration

Reading speed, character counting, sentence-final punctuation, and scan width come from
`config/language_profiles.json`. The shipped profiles cover `zh`, `zh-hant`, `ja`,
`ko`, `en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `ar`, `he`, `th`, `vi`, `id`, and `tr`.
Regional codes such as `en-US` use their base-language profile. An unknown code uses the
explicit `default` profile and must be mentioned in the report.

Line-level display budgets use Display Units (DU): full-width CJK characters count as
1.0 DU, Latin letters and digits count as 0.5 DU. The `max_width` profile parameter defines
the soft scan-comfort zone.

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

## Intermediate Artifacts and Cleanup

Keep runtime-created intermediates in the task workspace's `_temp/<unique-task-directory>`.
Without a workspace, use `%TEMP%/_temp/<unique-task-directory>`. Keep source files and
final deliverables outside it. Never overwrite or recycle unrelated pre-existing files.
Recycle this task's intermediates before delivery, including failed validation artifacts;
if cleanup fails, report the exact remaining paths rather than claiming success.

## Workflow

1. Read the complete source file and identify its domain, register, recurring terms,
   UI strings, likely ASR errors, and target language.
2. Read the references required by the format, language, domain, or warning being
   handled. Do not load unrelated references.
3. Audit source boundaries and pause proxies, then repair only nameable defects.
4. Translate sentence by sentence, without adding words to bridge repaired seams.
5. Apply the controlled-expression review: preserve the information payload (保留信息
   载荷), remove only zero-information filler, and check every condition, negation,
   number, hedge, and UI string.
6. Re-divide long translations at natural target-language thought boundaries. Never use
   a character count as the cutting rule.
7. Write UTF-8 output next to the source. For files over about 60 blocks, use
   `scripts/assemble_subtitle.py` to join numbered parts rather than pasting the result in
   the reply. It concatenates the parts verbatim and does **not** renumber, so each part
   must already carry its final sequential indices — or, equivalently, write the parts as
   plain `<start>|<end>|<text>` rows and let a small build step add the numbering.
8. Validate before replying:

   ```text
   python scripts/check_subtitle.py <output> --source <input> --lang <target>
   ```

   For bilingual or multi-speaker output, add `--max-lines 2`. For a user-requested
   untouched timeline, add `--strict`. Use `--lang-config` only when a project supplies
   a different profile file.

9. Fix every error. Review warnings for reading load, padding, dropped payload, markup,
   structure, and terminology; explain any deliberately retained warning.
10. After processing finishes, recycle the task workspace and every intermediate
   artifact created in this task, whether validation succeeds or fails. Follow the
   platform-safe procedure in [edge-cases.md](references/edge-cases.md), and report
   any remaining artifacts.

## Strict mode

Strict mode is explicit-user-request only. It requires the same block count, block order,
timestamp lines, SRT indices, VTT identifiers/settings, ASS non-Text fields, protected
markup, and format structure as the source. Only the dialogue wording may change.

Normal mode may merge or split within a continuous source span, and it may merge
across a source gap when the merge fixes a nameable defect. It must still preserve
format structure, protected markers, and source span coverage, and must report every
crossed source gap; it may not create a new gap.

## Delivery

Keep the final reply short: output path, mode and block count before/after, repair
categories (including removed or deliberately retained filler), every merge across a
source gap with its one-line reason, unresolved timing/ASR/terminology issues, checker
result, and one clause
confirming that self-created intermediate files were recycled. Do not put explanations,
citations, or translator notes inside subtitle text.

Use `source-zh.srt` for Simplified Chinese, `source-zh-hant.srt` for Traditional
Chinese, `source-en.srt` for English and the analogous `-<language code>` for other
targets. Use `-bi` in place of the language code for bilingual output.

## Reference routing

| Reference | Read when |
|---|---|
| `references/segmentation.md` | Every translation or boundary repair |
| `references/style-common.md` | Every translation |
| `references/style-zh.md` | Chinese target |
| `references/asd-ste100-subtitles.md` | Technical or instructional translation, or a request for concise, controlled, accurate, filler-free output |
| `references/names-zh.md` | Chinese target containing personal, historical, literary, fictional, stage, or uncertain names |
| `references/language-profiles.md` | Need human-readable profile explanations or custom calibration |
| `references/reading-load.md` | A duration, reading-speed, or scan-width warning needs judgement |
| `references/formats.md` | VTT, ASS, SSA, tags, or explicit conversion |
| `references/glossary-3d-zh.md` | 3D, motion graphics, or VFX into Chinese |
| `references/edge-cases.md` | Long files, encodings, bilingual output, anomalies, or cleanup |
| `scripts/check_subtitle.py` | Always, before replying |
