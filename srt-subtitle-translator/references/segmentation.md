# Segmentation Reference

Read this on every translation task. Segmentation is no longer a separate authorized
mode — repairing ASR breakage and placing boundaries where the *translation* breathes is
the default workflow. The only exception is strict mode (the user explicitly demanded an
untouched timeline), where you translate in place and only condense.

## Why boundaries matter more than they look

A viewer reads a subtitle in one glance. If a block ends in the middle of a grammatical
unit, the eye has to hold an incomplete structure in memory until the next block appears,
and the next block starts with something that means nothing on its own. Broadcast
guidelines all converge on the same principle: break at the highest syntactic node
available, so each block is a self-contained chunk.

ASR-generated subtitles ignore this completely. They cut on pause detection and on a
fixed character budget, which is why auto-captions strand articles, prepositions,
technical terms, and single trailing words. And the damage compounds in translation:
a boundary that merely looks awkward in English can be *impossible* in Chinese, because
the two languages order their sentences differently.

The mirror-image failure is over-merging: collapsing a long sentence into one wall of
text because "it is one sentence". That makes the subtitle unreadable in its time window
and destroys breaks the speaker actually made. Both failures are equally wrong; a large
drop in block count is a warning sign, not an achievement.

## Repair, translate, then divide

The fixed working order of this skill: **first repair orphan words and other ASR
breakage, then translate whole sentences, then divide the translation on the timeline.**
Shown on a real failure. Source, with an orphan tail:

```srt
4
00:00:03,985 --> 00:00:10,760
we are going to take a look at one of many methods on how to create variations of stuff

5
00:00:10,760 --> 00:00:12,445
using MoGraph.
```

The wrong way — translate each block in place to "preserve the timeline":

```srt
4
00:00:03,985 --> 00:00:10,760
介绍一种创建随机变化的方法

5
00:00:10,760 --> 00:00:12,445
使用 MoGraph
```

`使用 MoGraph` trails the sentence it belongs inside. Chinese puts the means *before*
the action — `用 MoGraph 创建随机变化` — so no placement of these two blocks can ever
read naturally. The boundary itself makes natural Chinese impossible.

The right way — merge the defect, translate the sentence whole, then fit the result to
the speech span:

```srt
4
00:00:03,985 --> 00:00:12,445
来看看用 MoGraph 创建随机变化的其中一种方法
```

Nineteen characters, one glance, natural word order. It spans 8.5 s — longer than the
7 s comfort anchor — but the speech simply lasts that long and the line is short;
explain the checker's duration warning rather than forcing a split with no natural seam.

Had the natural Chinese come out long — say 35 characters — the sentence would instead
be split at a *Chinese* phrase boundary and distributed across the same span,
proportionally to the speech:

```srt
4
00:00:03,985 --> 00:00:08,500
我们来看看其中一种方法

5
00:00:08,500 --> 00:00:12,445
用 MoGraph 为物体创建随机变化
```

Note the split point is not where English cut it — it is where the *Chinese* breathes.
That is always the test: every output block must be a phrase a native speaker of the
target language would say in one breath.

## Auditing the source: the two tests

Before translating, judge every source boundary on the source text:

1. **Completeness** — does the first block end on a complete phrase or clause?
2. **Independence** — can the second block be understood without borrowing a noun, verb,
   object, or complement from the first?

Either test fails → the boundary is an ASR defect; the blocks belong to one sentence and
are translated together. Both pass → the boundary marks a real phrase break in the
speech. Keep it *if the translation also breaks naturally there*; when the target
language's word order wants the break elsewhere, the sentence is still translated whole
and re-divided at its own seams — within the same continuous speech, never across a real
pause.

The Netflix Timed Text Style Guide lists what a break must never separate: an article
from its noun, an adjective from its noun, a first name from a last name, a subject
pronoun from its verb, a verb from its auxiliary or negation, a prepositional verb from
its preposition. That is exactly the inventory of ASR damage in an English source — and
the same principle applies to the boundaries you place in the target language.

## Orphan taxonomy

An orphan is any block-edge fragment that cannot work as a subtitle on its own.

| Type | Source pattern | Example |
|---|---|---|
| Sentence-completion tail | second block is only the last word or two of the sentence | `... in the geometry` / `nodes.` |
| Stranded connector | first block ends on article, preposition, conjunction, auxiliary, phrasal-verb particle | `... based on the` / `same technology.` |
| Dependent opening | second block opens as the object or complement of the first | `We can also add some` / `turbulence.` |
| Split term | a named entity, UI label, or technical term is cut in half | `Rope` / `Dynamics tag` |
| Trailing modifier | second block is a modifier the target language must move inside the sentence | `... create variations of stuff` / `using MoGraph.` |
| Flash block | a sub-second block carrying no idea of its own, produced by mechanical timing | `Right.` on screen for 0.14s |

All of these mean: translate the sentence as one unit. A flash block of pure filler
(`Okay`, `Right`) disappears in translation anyway; the merge gives the surviving text a
usable time window.

## The silence gap as evidence

The gap between one block's end and the next block's start is physical evidence:

- A **near-zero gap** is the signature of a mechanical ASR cut — the speaker did not
  pause there. Boundaries like this are freely re-placed to fit the translation.
- A **clear, audible silence** is a pause the speaker actually made — a
  breath, a topic shift, a beat before the next point. It is an audio anchor: no output
  block may span across it, whatever the grammar suggests. If a sentence genuinely
  straddles a long pause, each side gets its own block and the translation is
  distributed so that each side stands alone as target-language text.

## Placing boundaries in the translation

Once a sentence is translated whole, fit it to its speech span:

**One block** when the line reads in one glance (Chinese: within the ~12–25 character
scan-comfort zone) — even if the span is long; a short line over a long span beats an
artificial split.

**Split** when, after honest condensing, the line still fails a one-glance read, or it
carries two or more independent statements:

- Cut at a natural target-language phrase boundary: a `，` separating two statements, a
  clause edge, before a connective (但是/所以/然后/接着), between an operation and its
  consequence, between topic and comment. Each piece must be something a native speaker
  would say in one breath — the two tests above, applied to the target text.
- Place interior time points proportionally to the spoken material, snapped to source
  punctuation or an audible pause where the source shows one. The first piece starts
  where the speech starts, the last ends where it ends, and the pieces tile the span
  exactly.
- Each piece must be readable in its window — a piece that flashes by too fast to read
  means the split point is in the wrong place or the split was unnecessary.

The comfort zone (12–25 chars, ~1.8–4.5 s for Chinese) is calibration for "effortless",
never a quota. A 28-character line with no natural interior seam stays whole; a
20-character line carrying two separate statements still splits. Phrasing decides; the
numbers only tell you when to look.

## Keep real multi-block sentences multi-block

A long sentence whose source boundaries all fall on genuine phrase breaks — and whose
translation also breaks naturally at those points — keeps them:

```srt
4
00:00:18,505 --> 00:00:25,380
In this video, I'm going to give you a comparison to the old UV editor

5
00:00:25,380 --> 00:00:30,960
and provide you with a lay of the land so you know how to use it and potentially adapt

6
00:00:30,960 --> 00:00:33,700
some of your workflows to the new UV editor.
```

Boundary 4/5 breaks before a coordinating conjunction starting a full clause: a real
seam, and Chinese breaks naturally there too — keep. Boundary 5/6 strands `adapt` from
its object: a defect. Blocks 5 and 6 are translated as one unit and re-divided where the
Chinese breathes — the timestamps 25,380 and 33,700 anchor the span, and the interior
point moves to wherever the Chinese phrase boundary wants it. Collapsing all three
blocks into one 15-second block would be the opposite error.

## Self-check before writing the output

- Speech-span edges and every audible pause from the source survive untouched; no block
  crosses a real pause; within each span the blocks tile it exactly
- Every block is a single line and reads as a natural, self-contained target-language
  phrase — nothing in the file exists only because the source happened to cut there
- No block ends on a stranded connector; no block is a bare completion tail or a
  trailing modifier the target language wants inside the sentence
- No named term, UI label, or number+unit pair is split across a boundary
- Long sentences stay multi-block where real phrase breaks exist, in both languages
- Every merge fixes a specific, nameable defect; every added or moved boundary lands on
  a target-language seam, nameable the same way; no piece flashes by unread
- No boundary was placed, and no wording was cut, to satisfy a character count
- `scripts/check_subtitle.py --source <original>` reports zero errors

`check_subtitle.py` mechanically proves the audio claims (speech coverage, pauses
preserved, exact tiling, no overlap) and flags wrapped blocks, heavy merges, blocks
that exceed the reading-speed budget or the scan-comfort zone, and a suspiciously low
retention ratio. It cannot judge whether a boundary is natural in the target language —
that stays your job.
