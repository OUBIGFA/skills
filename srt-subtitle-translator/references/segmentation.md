# Segmentation Reference

Read this when the task authorizes re-segmentation (the user asked to merge fragments, fix
orphan words, re-split blocks, or to check whether any of that is needed). In
structure-preserving mode you never change boundaries, so you can skip this file.

## Why boundaries matter more than they look

A viewer reads a subtitle in one glance. If a block ends in the middle of a grammatical
unit, the eye has to hold an incomplete structure in memory until the next block appears,
and the next block starts with something that means nothing on its own. Broadcast
guidelines all converge on the same principle: break at the highest syntactic node
available, so each block is a self-contained chunk.

ASR-generated subtitles ignore this completely. They cut on pause detection and on a
fixed character budget, which is why auto-captions strand articles, prepositions,
technical terms, and single trailing words. Repairing those cuts is the whole job here.

The mirror-image failure is over-merging: collapsing a long sentence into one wall of
text because "it is one sentence". That makes the subtitle unreadable in its time window
and destroys breaks the speaker actually made. Both failures are equally wrong; a large
drop in block count is a warning sign, not an achievement.

The Netflix Timed Text Style Guide states the same principle as a line-treatment rule that
applies to every language: break **after punctuation, before conjunctions, before
prepositions**, and never let a break separate an article from its noun, an adjective from
its noun, a first name from a last name, a subject pronoun from its verb, a verb from its
auxiliary or negation, or a prepositional verb from its preposition. That list is written
for Indo-European grammar, but it is exactly the inventory of ASR damage you will find in
an English source, and it is the list to audit against before translating.

## The two tests, applied to the source language

Judge every boundary before translating, on the source text. Translation can hide a
broken source boundary by inventing two natural-sounding Chinese phrases, and that is
exactly the failure to avoid — the timing still splits the thought.

1. **Completeness** — does the first block end on a complete phrase or clause?
2. **Independence** — can the second block be understood without borrowing a noun, verb,
   object, or complement from the first?

Both yes → KEEP. Either no → MERGE the smallest adjacent group that fixes it.

Reasons that are *not* sufficient to merge: same sentence, same topic, same speaker, the
merged block would still be readable, fewer blocks looks tidier.

## Orphan taxonomy

An orphan is any block-edge fragment that cannot work as a subtitle on its own.

| Type | Source pattern | Example |
|---|---|---|
| Sentence-completion tail | second block is only the last word or two of the sentence | `... in the geometry` / `nodes.` |
| Stranded connector | first block ends on article, preposition, conjunction, auxiliary, phrasal-verb particle | `... based on the` / `same technology.` |
| Dependent opening | second block opens as the object or complement of the first | `We can also add some` / `turbulence.` |
| Split term | a named entity, UI label, or technical term is cut in half | `Rope` / `Dynamics tag` |
| Flash block | a sub-second block carrying no idea of its own, produced by mechanical timing | `Right.` on screen for 0.14s |

The first four are structural and must be repaired. A flash block is a readability
repair: merge it into whichever neighbour it belongs to semantically. If it is pure
filler (`Okay`, `Right`, `All right`), the filler disappears in translation anyway and the
merge simply gives the surviving text a usable time window.

## Repair order

1. Merge on the source text. The merged block spans the first block's start time and the
   last block's end time. No other timestamp may change, and no new timestamp may be
   invented.
2. Merge the smallest group that fixes the specific defect. A three-block merge is only
   legitimate when each removed boundary independently fails the two tests.
3. Only after the mandatory merges, redistribute Chinese wording across boundaries that
   already passed the tests, if that makes each block read more naturally.

## Worked examples

Sentence-completion tail — the second block only finishes the sentence:

```srt
7
00:01:13,930 --> 00:01:23,810
Cinema 4D 2026.3 is out now and we have a couple of cool features in there that we are

8
00:01:23,810 --> 00:01:25,575
going to show you.
```

Repaired:

```srt
7
00:01:13,930 --> 00:01:25,575
Cinema 4D 2026.3 is out now and we have a couple of cool features in there that we are going to show you.
```

Split technical term — `geometry nodes` is one term, so `nodes` cannot stand alone:

```srt
4
00:00:14,690 --> 00:00:19,380
It provides a lot of functionality and to do the cloth physics directly in the geometry

5
00:00:19,380 --> 00:00:19,905
nodes.
```

Repaired: one block, `00:00:14,690 --> 00:00:19,905`.

Long sentence that must stay multi-block — every boundary already falls on a clause or
phrase break, so collapsing it into one 15-second block would be the error:

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

Boundary 4/5 breaks before a coordinating conjunction that starts a full clause: KEEP.
Boundary 5/6 strands `adapt` from its object, and `some of your workflows...` opens as
that object: this one fails the tests. Because both blocks are otherwise substantial, the
right fix is redistribution rather than a merge — move `and potentially adapt` down to
the third block, keeping all three timestamps:

```srt
5
00:00:25,380 --> 00:00:30,960
and provide you with a lay of the land so you know how to use it

6
00:00:30,960 --> 00:00:33,700
and potentially adapt some of your workflows to the new UV editor.
```

Redistribution is only available while the text is still in the source language and only
across boundaries that are otherwise sound. It is not a way to launder a stranded term.

## One block, one line — never wrap

A block holds exactly one line of text. There is no characters-per-line limit, and no
situation in which the right answer is to wrap a block onto a second line.

This is not a cosmetic preference. A character budget has no way to tell a natural phrase
from an awkward one, so enforcing one guarantees breaks that land mid-phrase, and tempts
you to delete meaning just to get under the count. Both are worse than a line that is
simply a bit long. Players wrap long lines on their own; that automatic wrap is at worst
neutral, whereas a break you inserted at the wrong place is a defect baked into the file.

When a block reads too long, in order of preference:

1. **Condense.** Drop filler, use symbols and numerals, choose the shorter synonym. This is
   the default fix and usually the only one needed.
2. **Redistribute** across neighbouring blocks — source language, sound boundaries only,
   as in the worked example above.
3. **Re-audit the boundary**, if re-segmentation is authorized and the length is a symptom
   of a bad merge.

What is never acceptable: inserting a line break, or cutting words that carry meaning in
order to hit a length target. If the choice is between a slightly dense block and a
mangled sentence, keep the sentence — `check_srt.py` reports reading speed so you can see
how dense it actually is, in seconds rather than in characters.

A sentence that continues into the next block gets no ellipsis and no dash at either end;
the timing carries the continuation. Ellipses are for a real pause of two seconds or more,
or an interruption.

The only two-line cases are structural, not typographic: bilingual output (Chinese line,
source line) and multi-speaker blocks where each dash-prefixed speaker needs its own line.
See `references/edge-cases.md`.

## Self-check for re-segmentation

- Every output timestamp already existed in the input; nothing was shifted or interpolated
- Blocks renumbered sequentially from 1, all source text present exactly once in time order
- Every block is a single line — nothing was wrapped
- No block ends on a stranded connector, and no block is only a completion tail
- No named term, UI label, or number+unit pair is split across a boundary
- Long sentences remain multi-block wherever the retained boundaries are real phrase breaks
- Every removed boundary has a specific defect behind it, nameable in one phrase
- No boundary was moved, and no wording was cut, because of a character count
- `scripts/check_srt.py --source <original>` reports zero errors

`check_srt.py` mechanically proves the timeline claims (existing timestamps, full
coverage, no overlap) and flags wrapped blocks, blocks that merge three or more source
blocks, blocks that exceed the reading-speed budget, and a suspiciously low retention
ratio. It cannot judge whether a boundary was linguistically justified — that stays your
job.
