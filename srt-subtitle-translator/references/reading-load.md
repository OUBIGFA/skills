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

## Display Units (DU) and Line-Level Budget (行级显示单元预算)

Visual line width cannot be measured by a raw character count alone, because scripts
vary greatly in optical width. The framework evaluates horizontal load in **Display Units (DU)**:

- **CJK counting mode**:
  - 1 full-width CJK character (Han, Kana, Hangul, full-width punctuation) = **1.0 DU**
  - 1 half-width Latin letter, numeral, or ASCII symbol = **0.5 DU**
  - Ordinary punctuation in CJK subtitles has reading cost = **0**
- **Raw counting mode** (Latin/Cyrillic scripts):
  - Every character, space included = **1.0 DU**

### Soft Budget vs. Hard Budget

Two distinct thresholds govern visual comfort:

1. **Soft Budget (Scan Comfort Zone / 舒适视读区)**:
   - Chinese / Japanese / Korean: **18–25 DU** (`max_width: 25`)
   - Latin / English / European languages: **35–42 DU** (`max_width: 42`)
   - Lines inside the soft budget are scanned in a single, effortless fixation without
     horizontal eye movement.
2. **Hard Budget (Screen Width Cap / 视屏硬上限)**:
   - Chinese: **~30–32 DU**
   - Latin scripts: **~48–50 DU**
   - A subtitle crossing the hard budget crowds screen boundaries and forces active eye
     saccades. Any sentence exceeding the hard budget is an imperative candidate for
     pre-planned splitting.

### Pre-planning multi-piece cuts (`k ≥ 2` pieces with `¦`)

When translating a long source statement whose target rendering will clearly exceed the
hard budget, plan its division before committing to timestamps:
- Propose $k \ge 2$ balanced pieces using suggested cut markers (`¦`).
- Aim for each piece to settle comfortably within the soft budget (~12–20 DU) and last
  at least ~1.0 s.
- Always cut at natural syntactic seams (意群气口: after commas, before clausal
  connectives, or between topic and comment).
- Never split mechanically by character count: phrasing governs cuts, while Display Units
  tell you when to look.

For Chinese, the practical translation of the numbers: a 2-second block holds about 18
Display Units, not 30.

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
