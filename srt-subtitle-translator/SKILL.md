---
name: srt-subtitle-translator
description: Hand-translate subtitle files — SRT, WebVTT (.vtt), ASS/SSA (.ass) — into faithful, concise subtitles in the requested target language (Simplified Chinese by default). Fidelity to what the speaker actually said comes first, then the shortest comfortable wording that carries it, with nothing padded in for the sake of flow. Repairs ASR-broken segmentation, translates whole sentences, and re-places block boundaries for target-language word order and one-glance readability without crossing real speech pauses. Use this whenever the user asks to translate subtitles or captions in any direction, review or fix subtitle segmentation, merge fragmented ASR blocks, clean up auto-generated captions, produce bilingual subtitles, or hands over an .srt/.vtt/.ass file with any request at all — even a bare "translate this". Never route subtitle text through translation APIs, browser translation, online translators, or MT software; every line is translated by hand.
version: 5.1.0
---

# SRT Subtitle Translator

Turn a subtitle file — `.srt`, `.vtt`, or `.ass`, usually machine-transcribed, usually
noisy — into a subtitle file in the target language that says exactly what the speaker
said, in the fewest comfortable words, and that a viewer can read at speed without
pausing the video. The target language is whatever the user asks for; when they don't
say, it is Simplified Chinese.

## When to Use This Skill

- The user asks to translate subtitles or captions in any format or direction — into
  Chinese, English, Japanese, or any other language.
- The user wants to review or fix subtitle segmentation, merge fragmented ASR blocks, or
  clean up auto-generated captions.
- The user wants a bilingual subtitle file.
- The user hands over an `.srt`, `.vtt`, or `.ass` file with any request at all — even a
  bare "translate this".

## Scope and hard limits

- Fidelity to the source meaning is the top priority; concise, comfortable
  target-language wording is how that meaning gets delivered. Repair ASR-broken
  segmentation by default: orphan tails, split terms, stranded prepositions, flash blocks.
- Translate whole sentences, then re-place boundaries on the timeline to fit the target
  language's word order and one-glance readability — never crossing a real speech pause,
  never shifting where speech starts or stops.
- Never route subtitle text through third-party translation APIs, browser translation,
  online translators, or local MT software. The translation is done by hand, here.

Four things decide whether the result is good, in this order:

- **Fidelity.** The line says what the speaker said — the same claim, the same object,
  the same operation, the same hedge, the same degree, the same emphasis. Nothing added
  that wasn't in the audio, nothing dropped that carried information. This outranks
  everything below it: a smoother line that shifts the meaning is a worse subtitle than a
  slightly plainer line that keeps it.
- **Economy.** Once the meaning is fixed, the best wording is the shortest one that still
  carries it. A subtitle is read in a glance while the viewer is also watching the screen,
  so every character the viewer doesn't need is a real cost. Never pad a line to make it
  flow, to fill a time window, or to sound more polished than the speaker did — see
  *Faithful and lean* below.
- **Reading comfort.** Each block must be readable in its time window and scannable in
  one glance, and must read as a phrase a native speaker would actually say — word order,
  phrasing, and rhythm follow the target language, never the accidents of how ASR cut the
  source. A translation contorted to fit source block boundaries is a wrong translation.
  So is a rendering only insiders can parse: niche community shorthand loses to plain,
  self-explanatory target-language wording, and names the viewer watches being typed on
  screen are never translated at all.
- **Audio integrity.** The audio is the contract with the video — where speech starts,
  where it stops, and where the speaker actually paused. Those anchors are untouchable.
  Block boundaries *inside* a stretch of continuous speech are not audio; they are
  editorial choices, and they serve the target language.

Fidelity and economy pull in the same direction far more often than they conflict,
because most length in a bad subtitle comes from words the source never had. When they do
conflict — the faithful rendering genuinely needs more characters — keep the meaning and
accept the density, then look for a split. Compress wording, never content.

## Faithful and lean

This is the priority that most often gets lost, because the failure feels like good work
while you are doing it: the translation drifts *upward* — smoother, fuller, more
explanatory, more literary than the person actually talking.

The target is what a good human subtitler produces: the speaker's own meaning, at the
speaker's own register, in the fewest characters that carry it. Not a summary, not a
paraphrase, not an improvement.

| Source | Padded (wrong) | Lean (right) |
|---|---|---|
| `Move it up a bit` | `我们把它稍微向上移动一点距离` | `往上挪一点` |
| `Now add a bevel` | `接下来我们需要为它添加一个倒角效果` | `加个倒角` |
| `Set it to 20` | `把这个数值设置为 20 就可以了` | `设成 20` |

Every padded version above reads pleasantly, and every one of them puts words in the
speaker's mouth. The recurring sources: subjects the source left out (`我们`/`你`), stock
connectives inserted to make blocks flow (`接下来`/`那么`), category nouns glued onto verbs
and adjectives (`效果`/`操作`/`距离`), invented necessity or closers
(`我们需要`/`就可以了`), and degree words upgraded (`a bit` is not `很多`). Filler removal is
the opposite operation and stays: dropping `yeah`, `um`, `you know` removes noise, not
content.

Two tests, applied to every line before it is written: *would a native speaker say this out
loud?* and *is every word here traceable to something in the audio?*

Deletion has a bar too. Operations, parameter values, names, numbers, visual judgements,
warnings, causal links (`because…`, `otherwise…`), negation, and hedges that change how
certain the claim is (`probably`, `about`, `I think`) are payload. If a block is over-dense
after honest de-padding, split it or accept the density — never buy comfort with meaning.
And keep the speaker's register: casual speech stays casual (`往上挪一点`, not
`向上进行移动`), a formal lecture stays formal.

Full padding checklists: `references/style-common.md` for every target language,
`references/style-zh.md` for the Chinese-specific temptations (four-character-idiom polish,
and restoring the subjects and measure words spoken Chinese drops).

## The sentence is the translation unit

The working order is always: **repair the segmentation, then translate, then divide.**

1. **Repair the source segmentation first.** Merge genuine ASR breakage — orphan tails,
   split terms, stranded prepositions, flash blocks — so each unit is a complete thought.
2. **Translate the whole sentence** into the shortest target-language sentence that says
   everything the source said, with zero regard for where the source blocks were cut —
   and with nothing added to smooth the seam you just repaired.
3. **Then divide the translation on the timeline.** If it reads in one glance, it stays
   one block spanning the sentence's speech. If it is too long to read naturally, split
   *the translation* at the target language's own phrase boundaries and distribute the
   pieces across the sentence's time span, proportionally to the speech.

Never reverse this order. Boundaries exist to serve the translation; the translation never
bends to serve a boundary.

Why it matters, in one real case. ASR left `using MoGraph.` stranded as its own block after
`…on how to create variations of stuff`. Translating each block in place "to preserve the
timeline" produced `介绍一种创建随机变化的方法` / `使用 MoGraph` — and no placement of those
two blocks can ever read naturally, because Chinese puts the means *before* the action.
Merging the defect and translating the sentence whole gives
`来看看用 MoGraph 做出各种变化的其中一种方法`: twenty characters, one glance, natural word
order, and nothing in it the audio didn't have — no `我们`, no `接下来`, and `variations`
not upgraded into `随机变化`, a word the speaker never said.

Every output boundary must also leave both sides intact as thought units: no block ends on
a connective, preposition or governing verb whose complement lands in the next block, and
no block opens on a stranded particle. The full laws, the two-pass audit that catches
violations, and worked examples of splits are in `references/segmentation.md` — read it
before auditing or placing any boundary.

## Audio anchors — what may and may not move

May never change:

- Where speech starts and stops: the first block edge after silence and the last edge
  before silence come from the source
- Real pauses: a silence you can actually notice — a breath, a beat, a topic shift — is
  a pause the speaker made. No output block may span across it, and the gap survives in
  the output (the checker uses ~0.3 s as its mechanical proxy for "noticeable")
- Total coverage: all speech is subtitled; no speech time is dropped, no silence is
  stretched over

May change, in service of the target language:

- Any boundary *inside* continuous speech (tiny inter-block gaps are ASR jitter, not
  pauses). Merge across it to reunite a sentence; re-place it where the translated
  phrasing wants a break; remove it when one comfortable block covers the sentence
- New interior time points are placed proportionally to the spoken material, and the
  resulting pieces tile the speech span exactly — no overlaps, no invented gaps, and no
  piece so brief it flashes by unread

If the user explicitly needs the timeline byte-for-byte untouched (subtitles already
burned in, an external tool keyed to block indices), translate in place, condense as far
as meaning allows without breaking target-language word order, flag blocks that remain
over-long or unnatural, and verify with `--strict`.

## Formats

The output format is the input format. `.srt` in, `.srt` out; `.vtt` in, `.vtt` out;
`.ass` in, `.ass` out. Never convert silently — cue settings, styles, and positioning are
not representable across formats. Convert only on an explicit user request, and say what
will be lost.

Only the dialogue text is yours to translate. Everything else is structure and must
survive unchanged: the `WEBVTT` header, NOTE/STYLE/REGION blocks and cue settings in VTT;
`[Script Info]`, the styles section, field layout, and `{\...}` override tags in ASS;
formatting tags everywhere. Before touching a `.vtt` or `.ass` file, read
`references/formats.md`.

## Target language

Translate into the language the user asks for. `references/style-common.md` applies to
every target language. When the target is Chinese, `references/style-zh.md` applies on
top of it. For other targets, follow that language's own subtitle conventions — English
subtitles, for example, keep normal sentence-final punctuation; the no-final-punctuation
rule is a Chinese/Japanese convention, not a universal one.

## Manual translation only

Translate every line yourself, using context and domain knowledge. Do not call translation
APIs, online translators, browser translation, MT plugins, or local translation software,
and do not write scripts that call them. If asked to use one, say that this skill
translates by hand and continue manually unless the user changes the requirement.

Local tooling is fine for everything that is not translation: reading files, counting
blocks, validating structure, comparing timestamps, formatting output.

## Workflow

1. **Read the whole file first.** Not the first 50 blocks — the whole thing. You are
   looking for the domain, the speaker's habits and register, recurring UI labels and
   terms, and passages where ASR clearly misheard something. Decide the glossary now,
   before any line is translated; consistency across 300 blocks is impossible to retrofit.
   Where a glossary ships for the domain and target, start from it — for 3D and motion
   graphics into Chinese, `references/glossary-3d-zh.md`. It supplies defaults, not
   substitutions: one source term can need the UI wording in one line and spoken phrasing
   in the next. Anything the video shows being typed — object names, file names, presets —
   is kept verbatim.

2. **Audit the segmentation** in the source language: mark every ASR defect (orphan
   tails, split terms, stranded connectors, flash blocks) and every audible pause. This
   map — sentences and their speech spans — is what you translate from. Classifying
   boundaries after translation does not work.

3. **Repair, translate, then divide — in that order, sentence by sentence.** Merge the
   defects, render each sentence as the shortest target-language sentence that carries
   everything the source said, then fit it to its speech span: one block when it reads in
   one glance, split at target-language phrase boundaries when it does not. Every piece
   must read as a self-contained chunk in the target language; none may be empty; the whole
   sentence must not be dumped into one over-long block when a natural split exists.

   Re-read each finished batch before writing it, in this order: delete padding that crept
   in, then fix lines no native speaker would say (`搭建角色的大型`, `多边形环绕过髋部`,
   `取消勾选选中线框` — the taxonomy is in `references/style-zh.md`), then grep for variant
   renderings of the same term (`环形边` vs `循环边`); one concept, one rendering,
   mechanically checked.

4. **Write the output**, then **verify it mechanically**:

   ```bash
   python <skill>/scripts/check_subtitle.py <output> --source <input> --lang <target>
   ```

   `--lang` takes the target language (`zh` default, `ja`, `ko`, `en`, …). Errors mean
   the file is broken — speech uncovered, a block crossing a real pause, edges outside
   the source speech, overlap, bad numbering, a silent format change — and must be fixed
   before you reply. Warnings are reading-load, scan-comfort and length-fidelity problems;
   fix them or explain why they stand. Treat a length-fidelity warning as a prompt to
   re-read that span against the source: `check for padding` usually means words crept in
   that the audio never had, and `check for dropped payload` usually means an operation, a
   value or a hedge was summarized away. Pass `--strict` only when the user required an
   untouched timeline.

5. **Recycle every intermediate artifact** — once, and only once, the checker reports
   zero errors. Part files, the temp directory holding them, source dumps, span and
   glossary scratch files: all of it goes, leaving only the source and the delivered
   translation. **To the recycle bin, never a permanent delete** — no `rm`, no `del`, no
   `Remove-Item`. The Windows/macOS/Linux commands are in `references/edge-cases.md`.
   Recycle only what you created in this task, and never ask permission to clean up your
   own scratch — just do it before replying.

6. **Report briefly**: file path, what was repaired and re-placed (with block counts
   before → after), what needs a human eye, and one clause confirming the intermediates
   were recycled. Not the subtitle text itself.

## Delivery

Under ~60 blocks: inline in one code block is fine.

Above that: **write a file**, named source name + target language code + original
extension — Chinese uses a hyphenated suffix, `tutorial.srt` → `tutorial-zh.srt`; other
language examples retain their code style, such as `talk.vtt` → `talk.en.vtt` — UTF-8, in
the source's directory. A 300-block file pasted into a reply risks silent truncation, and
a subtitle that stops at block 240 with no warning is worse than no subtitle. For long
files, build parts in a temp directory and concatenate — details and the encoding, tag,
and bilingual rules are in `references/edge-cases.md`.

**The directory you leave behind holds the source and the translation, nothing else.**
Part files, temp directories, source dumps, and scratch notes are yours to clean up, and
cleanup is not optional or negotiable — recycle them after the checker passes, without
asking. Recycle bin only: never `rm`, `del`, or `Remove-Item`, so a wrong path stays
recoverable. Commands per platform, and the two safety rules, are in
`references/edge-cases.md`.

Never mix an explanation into the subtitle file. Never emit citation markers, translator
notes, or commentary inside subtitle text.

## Reading load

A block must be readable in its time window and takeable in one glance. The calibration —
duration bounds, per-language reading speed, scan-comfort width, and what to do when a
block busts its budget — lives in `references/reading-load.md`. Read it when a checker
warning needs a judgement call.

Three things worth carrying without looking it up:

- **The numbers are review triggers, not quotas.** There is deliberately no
  characters-per-line limit: a character budget cannot tell a natural phrase from an
  awkward one, and enforcing one causes the two failures this skill exists to prevent —
  text cut mid-phrase, and meaning deleted to hit a count.
- **An over-budget block is usually padding, not a timing problem.** Read it against the
  source and delete what the audio never had *before* touching the timeline. If it is
  genuinely all payload, condense; if condensing is not enough, split. Never condense past
  the meaning.
- **Two checker warnings act as near-guards**, because they catch what re-reading your own
  output cannot: over-merge (fewer than ~70% of the source blocks kept) and length fidelity
  (a span carrying far more or far less text than the file's own norm — padding, or dropped
  payload). Everything else the checker prints, apart from structural errors, is advisory.

## One block, one line

Every block is a single line of text. Do not wrap, do not split a block across two lines,
and never let a character count decide where text breaks. In ASS, inserting `\N` or `\n`
*is* wrapping; existing break tags in the source stay where they are.

When a block feels too long, the remedies in order are: strip what the source never said,
condense the remaining payload, split at a target-language phrase boundary, or re-audit a
merge that should not have happened — see `references/reading-load.md`. Never insert a line
break, and never delete meaningful words to reach a length.

Two exceptions, both structural rather than cosmetic: bilingual output (target line,
source line) and multi-speaker blocks where each dash-prefixed speaker needs its own line.
Both are covered in `references/edge-cases.md`.

## Structural rules

- Output format identical to input format; all non-dialogue structure preserved unchanged
- Speech-span edges (block edges adjacent to an audible pause, plus the file's first
  start and last end) come from the source; no block crosses a real pause
- Within a continuous speech span, output blocks tile the span exactly: the first starts
  at the span's start, the last ends at its end, each starts where the previous ended
  (source-preserved micro-gaps are fine); no piece so brief it flashes by unread
- All source content appears exactly once, in time order; no block is empty; every block
  is a natural, self-contained target-language chunk
- Every claim, value, name, operation and hedge in the source survives in the output;
  nothing is invented to smooth a line, fill a window, or raise its register
- One line of text per block; no wrapping (see the exceptions above)
- SRT: renumber sequentially from 1 whenever boundaries changed; blank line between
  blocks; UTF-8; no BOM required but harmless
- Merges: the smallest group that fixes a specific, nameable defect — "same sentence" and
  "same topic" are not defects; a large drop in block count is a warning sign, not a goal
- Strict mode (explicit user demand only): every edge byte-for-byte unchanged, no
  merging or splitting; condense only, and flag what could not be fixed

## Segmentation in one paragraph

Audit in the source language, translate, then place boundaries in the target language.
A source boundary inside continuous speech survives only if it will also be a natural
seam in the *translation* — if the second half cannot stand alone in the target
language's word order, the sentence is translated whole and re-divided where the target
language breathes. An audible pause is a pause the speaker made:
never merge across it; a near-zero gap is the signature of a mechanical ASR cut. "Same
sentence" alone is not a reason to merge — a long sentence whose natural phrase breaks
align with its source boundaries keeps them. Length and duration only tell you *when* to
look at a boundary; they never decide *where* a cut lands — every cut is a grammar and
phrasing decision in the target language. A boundary operation must not change the text's
length either: merging tempts you to add a bridging connective, splitting tempts you to
repeat the subject in each piece. Full taxonomy and worked examples:
`references/segmentation.md`.

## Style in one paragraph

Say what the speaker said, in as few characters as carry it. Strip filler and hesitation —
they cost characters and carry nothing — and add nothing the audio didn't have. Use symbols
and Arabic numerals (`-50`, `360°`, `20%`, `10×10`, `3cm`). Keep software names, UI labels,
and acronyms in the source form unless a stable target-language term is more familiar.
Build the glossary before translating and hold it for the whole file, starting from the
shipped one where the domain has it; it gives defaults, not substitutions, so context
decides between an on-screen label and spoken phrasing, and between the several target
words one source term can map to. Prefer plain descriptive wording over insider shorthand
(`基础形体` for *blocking*, not the spoken `大型`), keep verbatim what the viewer watches
being typed on screen, repair obvious ASR mishearings from context rather than translating
the error, and keep the speaker's register.

For Chinese targets: one half-width space between Chinese and Latin text or numerals —
never around Chinese words, so `但 吸引 ...` and `把 摩擦 关掉` are both wrong (either blend
into Chinese as `但吸引...`, or keep the English term and space it, `但 Attractor ...`, which
is usually the better choice for UI terms). No space between a number and its unit. No
sentence-final full stop at the end of a subtitle line — the cut in time already ends the
thought. Exclamation marks (`！`/`!`) are forbidden throughout: express tone through word
choice or convert to a declarative sentence. A genuine `？` may remain when its question
tone matters.

Also for Chinese, one block carries one thought. An internal `。` or `；` normally means two
completed thought units landed in one block — split them and place the pieces on the
timeline. Commas `，`, enumeration commas `、` and question marks `？` are normal inside one
thought and never justify a split by themselves. Use `：` only for a genuine explanation,
label or structural introduction, and do not treat it as an automatic split signal.
Structural speaker labels, UI labels, menu paths, code, and text the viewer sees typed stay
faithful to the source. Judge the thought structure rather than banning punctuation
wholesale.

Language-independent rules: `references/style-common.md`. Chinese typography, punctuation
and the padding checklist: `references/style-zh.md`. Term defaults for 3D and
motion-graphics videos: `references/glossary-3d-zh.md`.

## Files in this skill

| Path | Read it when |
|---|---|
| `references/segmentation.md` | Every translation task — before auditing or placing any boundary; defect taxonomy, merge tests, split rules, thought-unit laws, worked examples |
| `references/style-common.md` | Any translation task; the fidelity/economy rule and padding checklist, plus noise, symbol, unit, glossary, and ASR-repair rules for every target language |
| `references/style-zh.md` | The target language is Chinese; the Chinese padding checklist, spacing, punctuation, naturalness failure patterns, terminology |
| `references/reading-load.md` | A duration, chars-per-second or scan-width warning needs a judgement call; per-language calibration tables |
| `references/formats.md` | The file is `.vtt` or `.ass`/`.ssa` — before reading or writing it |
| `references/glossary-3d-zh.md` | The video is about 3D, motion graphics, or VFX and the target is Chinese — term defaults aligned on Cinema 4D's Simplified Chinese across every application, plus the context rules for choosing between them |
| `references/edge-cases.md` | Long files, odd encodings, tags and speaker labels, bilingual output, timing anomalies, what to report |
| `scripts/check_subtitle.py` | Always, before replying |

## Optional: streaming-platform punctuation

Netflix's Simplified Chinese guide drops commas and full stops entirely, using a single
space in their place, requires `⋯` (U+2026) for ellipses, forbids italics, and uses
`《》` for titles. If the user is delivering to a streaming platform or asks for
platform-compliant subtitles, follow the platform's guide for the target language and say
you switched. Otherwise keep the house style in the style references, which reads more
naturally for tutorial and web video.
