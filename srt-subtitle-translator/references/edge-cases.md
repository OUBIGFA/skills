# Edge Cases and Delivery

## Long files: never translate straight into the reply

A 20-minute tutorial is 300+ blocks and roughly 10–15k characters of Chinese. Pasting that
into a chat reply risks hitting the response limit and silently truncating the tail — the
user then has a file that stops at block 240 with no warning.

Rule of thumb: **under ~60 blocks, inline is fine; above that, write a file.**

Write it next to the source with a `.zh.srt` suffix
(`tutorial.srt` → `tutorial.zh.srt`), then report the path plus what you changed.
For bilingual output use `.bi.srt`.

When the file is long enough that one write would be unwieldy, build it in numbered parts
in a temp directory and concatenate:

```bash
cat part1.srt part2.srt part3.srt > "/path/to/name.zh.srt"
```

Each part must start and end on a block boundary with a trailing blank line, so
concatenation cannot fuse two blocks. After concatenating, run
`scripts/check_srt.py <output> --source <input>` — it will catch a lost or duplicated
block immediately.

## Encoding

Always write UTF-8. Read defensively: source files show up as UTF-8, UTF-8 with BOM,
GB18030, or UTF-16, and a wrong guess produces mojibake that then gets "translated".
`check_srt.py` decodes all four. If the source itself contains mojibake (already-corrupted
Chinese), tell the user rather than translating the garbage.

On Windows, a console in a legacy codepage will mangle CJK on stdout even when the file is
correct — verify the file, not the terminal echo.

## Timing anomalies in the source

| Symptom | Handling |
|---|---|
| Overlapping blocks (next start < current end) | Report it. In structure-preserving mode keep the timestamps untouched; in re-segmentation mode do not "fix" it by inventing times |
| Zero-length or reversed block | Preserve the line, translate the text, flag it in the summary |
| A gap between blocks | Normal — silence. Never stretch a block to fill it |
| A single block far too dense for its window | Condense the Chinese; you may not invent a split time, and you may not wrap it onto a second line |

## Markup inside subtitle text

Preserve, do not translate:

- Formatting tags: `<i>`, `<b>`, `<u>`, `<font color=...>` — keep them wrapped around the
  equivalent Chinese span
- Positioning tags: `{\an8}`, `{\pos(...)}` — keep at the start of the line
- Music/sound annotations: `[music]` → `[音乐]`, `♪` — keep the marker, translate the word
- Speaker labels: `- ` dashes for two speakers stay at line start; `JOHN:` → `John：`

## Hearing-impaired and multi-speaker files

Keep every dash-prefixed speaker line on its own line inside the block. Do not merge two
speakers into one line — the dash structure is the only cue for who is talking. This is
one of the two sanctioned exceptions to one-block-one-line; run `check_srt.py` with
`--max-lines 2` on such a file.

## Bilingual output

Only when asked. Chinese on the first line, source on the second, one block, no blank line
between them — the other sanctioned exception to one-block-one-line, so validate with
`--max-lines 2`. Bilingual blocks are twice as dense, so the reading-speed budget
effectively halves; keep the Chinese line short.

```srt
12
00:01:02,300 --> 00:01:05,120
把子步数降到 10
Turn the substeps down to 10
```

## Non-SRT input

If handed `.vtt`, `.ass`, or a transcript with no timing, say what you can do: translate
the text and hand back the same format. Do not silently convert formats — cue settings and
styling in `.vtt`/`.ass` are not representable in SRT and would be lost.

## What to report back

The final reply is not the subtitle file — it is a short account of what happened:

- Where the output file is
- Mode: structure preserved, or re-segmented (with the block count before → after)
- The categories of repair made (orphan tails, split terms, flash blocks), with one or two
  concrete examples rather than an exhaustive list
- Anything the user should look at: unrecoverable ASR passages, source timing anomalies,
  terminology choices that could reasonably have gone another way
- The verification result from `check_srt.py`

Keep it to a few lines. The user wants to know it is safe to use, not to read a report.
