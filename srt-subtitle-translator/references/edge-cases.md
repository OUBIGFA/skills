# Edge Cases and Delivery

## Long files: never translate straight into the reply

A 20-minute tutorial is 300+ blocks and roughly 10–15k characters of translation. Pasting
that into a chat reply risks hitting the response limit and silently truncating the tail —
the user then has a file that stops at block 240 with no warning.

Rule of thumb: **under ~60 blocks, inline is fine; above that, write a file.**

Write it next to the source, named source name + target language code + original
extension: `tutorial.srt` → `tutorial.zh.srt`, `talk.vtt` → `talk.en.vtt`,
`episode.ass` → `episode.zh.ass`. Then report the path plus what you changed.
For bilingual output use `.bi.` in place of the language code.

When the file is long enough that one write would be unwieldy, build it in numbered parts
in a temp directory and concatenate:

```bash
cat part1.srt part2.srt part3.srt > "/path/to/name.zh.srt"
```

Each part must start and end on a block boundary with a trailing blank line, so
concatenation cannot fuse two blocks. For VTT, only part 1 carries the `WEBVTT` header;
for ASS, only part 1 carries the sections above `[Events]`. After concatenating, run
`scripts/check_subtitle.py <output> --source <input>` — it will catch a lost or
duplicated block immediately.

## Encoding

Always write UTF-8. Read defensively: source files show up as UTF-8, UTF-8 with BOM,
GB18030, or UTF-16, and a wrong guess produces mojibake that then gets "translated".
`check_subtitle.py` decodes all four. If the source itself contains mojibake
(already-corrupted text), tell the user rather than translating the garbage.

On Windows, a console in a legacy codepage will mangle CJK on stdout even when the file is
correct — verify the file, not the terminal echo.

## Timing anomalies in the source

| Symptom | Handling |
|---|---|
| Overlapping blocks (next start < current end) | Report it, and do not "fix" it by inventing times outside the speech span. In ASS, layered/positioned events overlap by design — leave them |
| Zero-length or reversed block | Preserve the line, translate the text, flag it in the summary |
| A gap between blocks | Normal — silence. Never stretch a block to fill it |
| A single block far too dense or too long for one glance | Condense first; if it still fails a one-glance read, split at a natural target-language phrase boundary within the speech span (see `references/segmentation.md`). Never wrap it onto a second line |

## Markup inside subtitle text

Preserve, do not translate:

- Formatting tags: `<i>`, `<b>`, `<u>`, `<font color=...>` — keep them wrapped around the
  equivalent translated span
- Positioning tags: `{\an8}`, `{\pos(...)}` — keep at the start of the line
- Music/sound annotations: `[music]` → translate the word, keep the bracket marker
  (`[音乐]` for Chinese); `♪` stays
- Speaker labels: `- ` dashes for two speakers stay at line start; `JOHN:` → `John：`
  (or the target language's convention)

VTT voice/class/karaoke tags and ASS override tags have their own rules — see
`references/formats.md`.

## Hearing-impaired and multi-speaker files

Keep every dash-prefixed speaker line on its own line inside the block. Do not merge two
speakers into one line — the dash structure is the only cue for who is talking. This is
one of the two sanctioned exceptions to one-block-one-line; run `check_subtitle.py` with
`--max-lines 2` on such a file.

## Bilingual output

Only when asked. Target language on the first line, source on the second, one block, no
blank line between them — the other sanctioned exception to one-block-one-line, so
validate with `--max-lines 2`. Bilingual blocks are twice as dense, so the reading-speed
budget effectively halves; keep the translated line short.

```srt
12
00:01:02,300 --> 00:01:05,120
把子步数降到 10
Turn the substeps down to 10
```

## Format handling

`.srt`, `.vtt`, and `.ass`/`.ssa` are all handled natively — same format in, same format
out, structure preserved; the format-specific rules are in `references/formats.md`. A
transcript with no timing gets its text translated and handed back in the same shape,
with a note that no timeline work was possible. Never silently convert between formats —
cue settings and styling are not representable across them and would be lost; convert
only on explicit request, stating the losses.

## What to report back

The final reply is not the subtitle file — it is a short account of what happened:

- Where the output file is
- Mode: structure preserved, or re-segmented (with the block count before → after)
- The categories of repair made (orphan tails, split terms, flash blocks), with one or two
  concrete examples rather than an exhaustive list
- Anything the user should look at: unrecoverable ASR passages, source timing anomalies,
  terminology choices that could reasonably have gone another way
- The verification result from `check_subtitle.py`

Keep it to a few lines. The user wants to know it is safe to use, not to read a report.
