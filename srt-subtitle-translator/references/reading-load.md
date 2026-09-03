# Reading-Load Reference

Calibration for "can the viewer read this block in the time it is on screen, in one
glance". Read it when a checker warning about duration, chars-per-second, or scan width
needs a judgement call, or when a project specifies its own numbers.

**None of the numbers here is a rule.** They are reference points for what comfortable
usually looks like, taken from the Netflix Timed Text Style Guides. The decision is always
qualitative: a block outside every anchor that reads effortlessly is correct; a block
inside every anchor that reads awkwardly is not. `scripts/check_subtitle.py` measures all
of it, per format and per target language, and every numeric finding it prints is a
warning — advisory — never an error.

## Timing

| Parameter | Value |
|---|---|
| Lines per block | 1 — always (bilingual and multi-speaker are the two exceptions) |
| Minimum duration | 20 frames ≈ 0.83 s |
| Maximum duration | 7 s |
| Minimum gap between blocks | 2 frames |
| Minimum duration of a re-split piece | ~1 s — below that it flashes by unread |

## Reading speed and scan comfort, per target language

Adult / children's programming where the guides differ.

| Target | Reading speed | Scan comfort | Counting |
|---|---|---|---|
| Chinese (zh) | 9 / 7 chars per second | 12–25 chars, review past ~25 | full-width char = 1, Latin letter or digit = 0.5, punctuation free |
| Japanese (ja) | 4 chars per second | review past ~25 | same as Chinese |
| Korean (ko) | 12 / 9 chars per second | review past ~25 | same as Chinese |
| English (en) | 20 / 17 chars per second | review past ~42 | every character, spaces included |
| Other Latin-script | ~17 / 13 chars per second | review past ~42 | every character, spaces included |

These are two independent constraints. Reading speed asks *is there enough time*; scan
comfort asks *can the eye take the line in whole*. A slow 8-second block passes reading
speed and can still be a 40-character wall — split it at a target-language phrase
boundary. For Chinese, ~1.8–4.5 s per block is where the rhythm feels natural.

The reverse case is legitimate and common: a long duration carrying a short, comfortable
line, because the speech simply lasts that long. Explain the checker's duration warning
rather than inventing a split with no natural seam.

## Why there is no characters-per-line limit

A character budget cannot tell a natural phrase from an awkward one, and enforcing one
produces exactly the two failures this skill exists to prevent: text cut mid-phrase, and
meaning deleted to hit a count. The comfort zone is a review trigger, not a quota.

For Chinese, the practical translation of the numbers: a 2-second block holds about 18
characters, not 30.

## When a block busts its budget

In this order:

1. **Check for padding first.** A block over its reading-speed budget is usually not a
   timing problem — it is words the audio never had. Read it against the source and delete
   whatever is not traceable there (`references/style-common.md` has the pattern list).
2. **Condense the remaining payload.** Shorter synonym, symbol instead of a spelled-out
   word, numeral instead of a number word.
3. **Split** at a natural target-language phrase boundary and distribute across the speech
   span, proportionally to the spoken material.
4. **Re-audit the segmentation.** The length may be the symptom of a merge that should
   never have happened.

Never: insert a line break, or delete meaningful words to reach a length.

## The two near-guards

Most checker warnings are advice. Two deserve to be treated as guards, because they detect
things you cannot see by re-reading your own output:

- **Over-merge** — an output keeping fewer than ~70% of the source blocks. Either every
  removed boundary answers to a nameable defect, or the file was flattened.
- **Length fidelity** — a speech span carrying far more or far less text than the rest of
  the file does for the same amount of source speech. More is the signature of padding;
  less, of dropped payload. The checker compares each span against the file's own median
  ratio, so it self-calibrates to the language pair and to bilingual output.

## Length that is too short

A line much shorter than a long, information-dense stretch of speech is not an
achievement — it usually means something was summarized away. Both directions of drift are
defects, and `check_subtitle.py --source` reports both.
