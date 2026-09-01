---
name: srt-subtitle-translator
description: Hand-translate subtitle files — SRT, WebVTT (.vtt), and ASS/SSA (.ass) — into natural, professional subtitles in the requested target language (Simplified Chinese by default), with no machine-translation services. The skill repairs ASR-broken segmentation, translates whole sentences, and re-places block boundaries on the timeline for target-language word order and one-glance readability, without crossing real speech pauses. Use this whenever the user asks to translate subtitles or captions in any format or direction, review or fix subtitle segmentation, merge fragmented ASR blocks, clean up auto-generated captions, produce bilingual subtitles, or hands over an .srt/.vtt/.ass file with any request at all — even a bare "translate this". Never route subtitle text through third-party translation APIs, browser translation, online translators, or local MT software.
version: 4.5.0
---

# SRT Subtitle Translator

Turn a subtitle file — `.srt`, `.vtt`, or `.ass`, usually machine-transcribed, usually
noisy — into a subtitle file in the target language that reads as if it had been written
in that language, and that a viewer can read at speed without pausing the video. The
target language is whatever the user asks for; when they don't say, it is Simplified
Chinese.

## When to Use This Skill

- The user asks to translate subtitles or captions in any format or direction — into
  Chinese, English, Japanese, or any other language.
- The user wants to review or fix subtitle segmentation, merge fragmented ASR blocks, or
  clean up auto-generated captions.
- The user wants a bilingual subtitle file.
- The user hands over an `.srt`, `.vtt`, or `.ass` file with any request at all — even a
  bare "translate this".

## Scope and hard limits

- Natural target-language expression is the top priority. Repair ASR-broken segmentation
  by default: orphan tails, split terms, stranded prepositions, flash blocks.
- Translate whole sentences, then re-place boundaries on the timeline to fit the target
  language's word order and one-glance readability — never crossing a real speech pause,
  never shifting where speech starts or stops.
- Never route subtitle text through third-party translation APIs, browser translation,
  online translators, or local MT software. The translation is done by hand, here.

Three things decide whether the result is good, in this order:

- **Natural target-language expression.** The viewer reads the translation, not the
  transcript. Word order, phrasing, and rhythm follow the target language — never the
  accidents of how ASR happened to cut the source. A translation contorted to fit source
  block boundaries is a wrong translation. So is a rendering only insiders can parse:
  niche community shorthand loses to plain, self-explanatory target-language wording,
  and names the viewer watches being typed on screen are never translated at all.
- **Reading comfort.** Each block must be readable in its time window and scannable in
  one glance. Condensing is part of the job; so is splitting a line no eye can take in
  whole.
- **Audio integrity.** The audio is the contract with the video — where speech starts,
  where it stops, and where the speaker actually paused. Those anchors are untouchable.
  Block boundaries *inside* a stretch of continuous speech are not audio; they are
  editorial choices, and they serve the target language.

## The sentence is the translation unit

The failure this rule exists to prevent, from a real delivery. Source, with a classic
ASR orphan tail:

```srt
4
00:00:03,985 --> 00:00:10,760
we are going to take a look at one of many methods on how to create variations of stuff

5
00:00:10,760 --> 00:00:12,445
using MoGraph.
```

Translating block-by-block to "preserve the timeline" produced:

```srt
4
00:00:03,985 --> 00:00:10,760
介绍一种创建随机变化的方法

5
00:00:10,760 --> 00:00:12,445
使用 MoGraph
```

This is wrong — not slightly wrong, structurally wrong. Chinese puts the means before
the action: `使用 MoGraph 创建随机变化`. Keeping the English boundary forced the
modifier to trail the sentence it belongs inside, which no Chinese speaker would ever
say. The correct output merges the broken boundary and translates the sentence as one
natural Chinese sentence:

```srt
4
00:00:03,985 --> 00:00:12,445
来看看用 MoGraph 创建随机变化的其中一种方法
```

So the working order is always: **repair the segmentation, then translate, then divide.**

1. **Repair the source segmentation first.** Merge genuine ASR breakage — orphan tails,
   split terms, stranded prepositions, flash blocks — so each unit is a complete thought.
2. **Translate the whole sentence** into the most natural target-language sentence,
   with zero regard for where the source blocks were cut.
3. **Then divide the translation on the timeline.** If it reads in one glance, it stays
   one block spanning the sentence's speech. If it is too long to read naturally, split
   *the translation* at the target language's own phrase boundaries and distribute the
   pieces across the sentence's time span, proportionally to the speech.
4. **Enforce Semantic Closure & Universal Thought-Unit Boundaries:**
   - **Law of Semantic Closure**: Every block must be an intact, self-contained thought unit. Never leave governing verbs that take a clausal complement (e.g. "看看", "试图", "准备", "想要") stranded at the tail of a block.
   - **Law of Clausal Introducer Head-Attachment**: Connectives and prepositions (因为/所以/如果/但是/然后/关于/为了/把/让/由) syntactically lead their clause; they MUST belong to the **start of the continuation block**, never trailing the prior block.
   - **Two-Pass Auditing**: Always run the *Forward Suspension Test* (does reading Block A feel cut off in mid-air?) and *Isolated Meaning Test* (can Block B stand as a natural spoken phrase?) across all continuous speech block pairs.

Never reverse this order. Boundaries exist to serve the translation; the translation
never bends to serve a boundary.

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

Before touching boundaries, read `references/segmentation.md` — it carries the defect
taxonomy, the merge tests, the split rules, and worked examples including the one above.

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
   looking for the domain, the speaker's habits, recurring UI labels and terms, and
   passages where ASR clearly misheard something. Decide the glossary now, before any line
   is translated; consistency across 300 blocks is impossible to retrofit. When a glossary
   ships for that domain and target, start from it rather than deriving terms yourself —
   for 3D and motion graphics into Chinese, that is `references/glossary-3d-zh.md`. It
   supplies defaults; the sentence's context still decides, since one source term can need
   the UI wording in one line and spoken phrasing in the next. Test every chosen term for
   **self-explanatoriness**: a viewer outside the niche must be able to roughly guess the
   meaning from the characters themselves (`基础形体` for *blocking* — not the spoken
   shorthand `大型`). Anything the video shows being typed — object names, file names,
   presets — is kept verbatim, never translated.

2. **Audit the segmentation** in the source language: mark every ASR defect (orphan
   tails, split terms, stranded connectors, flash blocks) and every audible pause. This
   map — sentences and their speech spans — is what you translate from. Classifying
   boundaries after translation does not work.

3. **Repair, translate, then divide — in that order, sentence by sentence.** Merge the
   defects, render each sentence as the most natural target-language sentence, then fit
   it to its speech span: one block when it reads in one glance, split at
   target-language phrase boundaries when it does not. Every piece must read as a
   self-contained chunk in the target language; none may be empty; the whole sentence
   must not be dumped into one over-long block when a natural split exists. While
   translating, keep one test in mind — *would a native speaker say this line out
   loud?* — and re-read each finished batch before writing it: fix verb–object pairings
   no native speaker produces (`搭建角色的大型`), garden-path segmentations
   (`多边形环绕过髋部`), and adjacent identical characters that jam parsing
   (`取消勾选选中线框`). Then grep the draft for variant renderings of the same term
   (`环形边` vs `循环边`); one concept, one rendering, mechanically checked.

4. **Write the output**, then **verify it mechanically**:

   ```bash
   python <skill>/scripts/check_subtitle.py <output> --source <input> --lang <target>
   ```

   `--lang` takes the target language (`zh` default, `ja`, `ko`, `en`, …). Errors mean
   the file is broken — speech uncovered, a block crossing a real pause, edges outside
   the source speech, overlap, bad numbering, a silent format change — and must be fixed
   before you reply. Warnings are reading-load and scan-comfort problems; fix them or
   explain why they stand. Pass `--strict` only when the user required an untouched
   timeline.

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

## Reading-load anchors

**None of the numbers in this section is a rule.** They are calibration — reference
points for what "comfortable" usually looks like, taken from the Netflix Timed Text
Style Guides. The decision itself is always qualitative: does this block read naturally,
in one glance, in the time it is on screen? A block outside every anchor that reads
naturally is correct; a block inside every anchor that reads awkwardly is not. The one
numeric guard in the whole skill is the checker's over-merge warning — an output that
keeps fewer than ~70% of the source blocks is flagged for review. Everything else the
checker prints, apart from structural errors, is advisory.

Timing calibration:

| Parameter | Value |
|---|---|
| Lines per block | 1 — always |
| Minimum duration | 20 frames ≈ 0.83 s |
| Maximum duration | 7 s |
| Minimum gap between blocks | 2 frames |

Reading speed, per target language (adult / children's programming):

| Target | Reading speed | Scan comfort | Counting |
|---|---|---|---|
| Chinese (zh) | 9 / 7 chars per second | 12–25 chars, review past ~25 | full-width char = 1, Latin letter or digit = 0.5, punctuation free |
| Japanese (ja) | 4 chars per second | review past ~25 | same as Chinese |
| Korean (ko) | 12 / 9 chars per second | review past ~25 | same as Chinese |
| English (en) | 20 / 17 chars per second | review past ~42 | every character, spaces included |
| Other Latin-script | ~17 / 13 chars per second | review past ~42 | every character, spaces included |

The scan-comfort zone is the second, independent constraint: reading speed asks "is
there enough time", scan comfort asks "can the eye take the line in one glance". A slow,
8-second block can pass reading speed and still be a 40-character wall — split it at a
target-language phrase boundary. For Chinese, ~1.8–4.5 s per block is where rhythm feels
natural. A long duration with a short, comfortable line is acceptable when the speech
span simply is that long — explain the checker's duration warning rather than inventing
a split with no natural seam.

There is deliberately **no hard characters-per-line limit** — the comfort zone is a
review trigger, not a quota. A character budget cannot tell a natural phrase from an
awkward one, and enforcing one produces exactly the two failures this skill exists to
prevent: text cut mid-phrase, and meaning deleted to hit a count. When a line runs past
the zone, the remedies are condensing and phrase-boundary splits — never a mechanical
cut.

What the timing values mean in practice: for Chinese, a 2-second block holds about 18
characters, not 30. When the translation runs long, condense — drop filler, use symbols
and numerals, prefer the shorter synonym. Cramming is a translation failure, not a timing
problem. When condensing alone cannot bring a block back to a one-glance read, split it.
But never condense past the meaning: if the choice is between a slightly dense block and
a mangled sentence, keep the sentence.

`scripts/check_subtitle.py` measures all of this, per format and per target language.

## One block, one line

Every block is a single line of text. Do not wrap, do not split a block across two lines,
and never let a character count decide where text breaks. In ASS, inserting `\N` or `\n`
*is* wrapping; existing break tags in the source stay where they are.

When a block feels too long, the answer is always one of:

1. **Condense** the translation — this is the first fix,
2. **Split** at a natural target-language phrase boundary and distribute across the
   speech span, or
3. **Re-audit** the sentence's segmentation — the length may be the symptom of a merge
   that never should have happened.

Never: insert a line break, or delete meaningful words to reach a target length.

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
phrasing decision in the target language. Full taxonomy and worked examples:
`references/segmentation.md`.

## Style in one paragraph

Strip filler and hesitation — they cost characters and carry nothing. Use symbols and
Arabic numerals (`-50`, `360°`, `20%`, `10×10`, `3cm`). Keep software names, UI labels,
and acronyms in the source form unless a stable target-language term is more familiar.
Build the glossary before translating and hold it for the whole file — and where a
glossary ships for the domain, start from it rather than deriving terms yourself. It
gives defaults, not substitutions: context decides between an on-screen label and spoken
phrasing, and between the several target words one source term can map to. Prefer plain descriptive wording over insider shorthand for concepts, keep verbatim what
the viewer watches being typed on screen, and repair
obvious ASR mishearings from context rather than translating the error. For Chinese
targets: one half-width space between Chinese and Latin text or numerals, none between a
number and its unit, and normally no sentence-final full stop at the end of a subtitle
line — the cut in time already ends the thought. Exclamation marks (`！`/`!`) are strictly
forbidden across all subtitles — express tone through natural phrasing or convert to
declarative sentences. A genuine `？` may remain when its question tone matters. Language-independent rules:
`references/style-common.md`. Chinese typography and punctuation:
`references/style-zh.md`. Term defaults for 3D and motion-graphics videos:
`references/glossary-3d-zh.md`.

For Chinese targets, apply the single-thought rule: one subtitle block should carry one
complete thought. An internal full stop `。` or semicolon `；` normally means the block
contains two completed or separately divided thought units; split them into separate
subtitle blocks and place the pieces on the timeline. Commas `，`, enumeration commas
`、`, and question marks `？` are normal punctuation inside one
thought and must not trigger a split by themselves (exclamation marks `！`/`!` are
prohibited throughout). Use a colon `：` only when a genuine
explanation, label, or structural introduction needs it, but do not treat it as an
automatic split signal. Structural speaker labels, UI labels, menu paths, code, and text
the viewer sees typed stay faithful to the source. Judge the thought structure rather
than banning punctuation wholesale.

## Files in this skill

| Path | Read it when |
|---|---|
| `references/formats.md` | The file is `.vtt` or `.ass`/`.ssa` — before reading or writing it |
| `references/segmentation.md` | Every translation task — before auditing or placing any boundary |
| `references/style-common.md` | Any translation task; noise, symbol, unit, glossary, and ASR-repair rules for every target language |
| `references/style-zh.md` | The target language is Chinese; spacing, punctuation, and terminology rules |
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
