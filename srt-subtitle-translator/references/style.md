# Style Reference

Everything here serves one goal: a viewer reads the subtitle once, at speed, and gets the
meaning without re-reading. Chinese subtitles are read faster than they are "translated"
in the viewer's head, so density and rhythm matter as much as accuracy.

## Noise filtering

Spoken tutorials are full of tokens that carry no information. Removing them is not
liberty-taking — it is what makes the line readable in its time window.

Remove when used as filler, hesitation, or self-agreement:

- English: `yeah`, `okay`, `alright`, `nice`, `cool`, `uh`, `um`, `like`, `you know`,
  `sort of`, `I mean`, `right?` as a tag question
- Chinese: 嗯、哦、呃、这个、那个、就是说、实际上

Keep the same words when they carry meaning:

- `Click OK` → `点击确定`（UI 按钮）
- `keep it cool` → `保持低温`
- `Is that right?` asked as a real question → keep the question

Condense fragmented self-talk instead of transcribing it:

- `Cool, let's check this, yeah, maybe this is okay` → `我们来检查一下，这样基本可以`
- `I mean, like, maybe just move this over here` → `可以把它移到这里`

Never remove: operations, parameter values, object or menu names, visual judgements,
warnings, causal explanations ("because…", "otherwise…"). Those are the payload.

## Symbols and numbers

Symbols read faster than spelled-out words and save horizontal space.

| Spoken | Write |
|---|---|
| negative 50 | -50 |
| 360 degrees | 360° |
| 20 percent | 20% |
| 10 by 10 | 10×10 |
| from 10 to 20 | 10~20 |
| greater than 5 / less than 3 | >5 / <3 |
| plus or minus 5 | ±5 |

Use Arabic numerals for settings, counts, frames, steps, versions, and any value the user
types into a field. Spell out numbers only in idiomatic phrases (`第一步`、`一点点`).

## Units

Use standard symbols, attached to the number with no space: `50kg`、`100m`、`220V`、
`50Hz`、`500nits`、`3cm`、`24fps`. Do not expand them into Chinese words
（`50千克` reads slower and takes more space）.

## Chinese-English typography

House style, not a platform requirement — Netflix's Simplified Chinese guide is silent on
CJK/Latin spacing, but the space makes mixed lines noticeably easier to scan:

- One half-width space between Chinese text and Latin words, numerals, software names,
  abbreviations, and UI labels: `在 C4D 中设置 100%，亮度为 500nits`
- No space between a number and its unit symbol, and no space around punctuation
- Use full-width Chinese punctuation inside the line（`，、：；`）and half-width numerals
  (`1, 2, 3`, never `１２３`)

Wrong: `在C4D中设置100%,亮度为500nits`

## Punctuation at line ends

Subtitles are timed, not typeset — the cut in time already ends the thought, so a trailing
full stop adds a character and no information. Do not end a subtitle text line with
`。．.` `!！` `?？` `;；` `:：` `，,` `、`.

Punctuation *inside* a line is fine and often necessary for parsing:
`把子步数降到 10，这样反而更稳定`.

A sentence that runs into the next block gets no ellipsis, no dash, no trailing comma —
the timeline carries the continuation. Reserve `⋯`(U+2026) for a pause of two seconds or
more, or an interruption.

Keep a question's force through wording rather than a question mark: `这样是不是更好`.
When a real question would be ambiguous without it, a full-width `？` is allowed.

No emoji, no citation markers, no translator notes, no bracketed commentary.

### Streaming-platform variant

If the user wants Netflix-compliant subtitles, their Simplified Chinese guide differs from
the house style above: commas and full stops are dropped entirely and replaced by a single
space, `、` may join list items but not end a line, italics are forbidden, quotation marks
are full-width `""`, and work titles take `《》`. Switch only on request, and say so.

## Names and terminology

- Personal names stay in their Latin form; romanize non-Latin names rather than
  transliterating into Chinese characters
- Software, renderers, plugins, algorithms, file formats, and acronyms stay in English
  unless a stable Chinese term exists and is more familiar than the English one
- On first appearance of an important concept, `中文（English）` is worth the extra
  characters; afterwards use the short form alone
- Menu paths, buttons, and parameter names are what the viewer must find on screen. If the
  software they are watching ships an English UI, keep the label in English. If the
  Chinese UI is standard for that tool, use the Chinese label.

**Build a glossary before translating.** Scan the whole file first, list every recurring
term and UI label, decide one rendering for each, and hold it for the entire file. An
inconsistent glossary is the most common defect in long tutorial subtitles — the same
button called three different things in twenty minutes.

### Example glossary — 3D / motion graphics tutorials

Keep in English: `Cinema`（Cinema 4D）、`Redshift`、`Noise`、`Volume`、`Fields`、
`Beauty`、`Bucket Rendering`、`Loft`、`Remesh`、`Sweep`、`Regular Grid`、`Rope Dynamics`

Translate:

| English | 中文 |
|---|---|
| Plane | 平面 |
| Material | 材质 |
| Light | 灯光 |
| Lighting | 布光 |
| Displacement | 置换 |
| Mask | 遮罩 |
| Commander | 管理器 |
| Viewport | 视窗（不译作"视口"） |
| Example | 案例（教学案例语境下不译作"示例"） |

This table is an example of the *shape* a glossary takes, not a universal mapping. For a
cooking, finance, or medical video, build the equivalent list for that domain.

## ASR error repair

Auto-captions mishear words that the context makes obvious. Repair the meaning rather
than translating the mistake:

- `road track` in a rope-simulation tutorial → the speaker said `Rope tag`
- `Powerbill` → `power bill`（电费）
- Numbers misheard as words, or a product name mangled into common words

Use the surrounding blocks and the domain to infer intent. When you genuinely cannot
recover the meaning, translate what is there and keep it readable — never leave a block
blank and never refuse the file because parts of it are noisy.

Repairs stay inside the block they belong to; do not move content across boundaries to
"fix" the transcript (in re-segmentation mode, repairs go into the merged block).
