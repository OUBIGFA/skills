# Style Reference — Chinese target

Rules that apply when the target language is Chinese, on top of
`references/style-common.md`. Chinese subtitles are read faster than they are
"translated" in the viewer's head, so density and rhythm matter as much as accuracy —
and Chinese carries more meaning per character than English, so a faithful translation
is usually too long until condensed.

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

## Natural spoken phrasing

A subtitle line must be something a native speaker would say out loud. Three failure
patterns from real deliveries — check every finished batch for them before writing:

- **Impossible verb–object pairings.** `搭建角色的大型` ("build the character's
  large-ness") — the noun is spoken shorthand that cannot take 搭建. Rewrite the idea
  with a real collocation: `搭建角色的基础形体`. If no natural collocation exists, the
  noun itself is insider slang and needs a plain-language replacement, not a better verb.
- **Garden-path segmentations.** Adjacent characters that invite a wrong parse:
  `多边形环绕过髋部` (多边形/环绕/过), `眼睛形状的观感受周围形状影响` (观感/受 vs
  观/感受), `在眼里得到两条环` (眼里 read as "in one's mind"). Rephrase so the intended
  parse is the only one: `这圈多边形绕过髋部`, `观感取决于周围形状`, `眼睛内部的两条环`.
- **Adjacent identical characters.** `取消勾选选中线框` jams on 取消勾选＋选中. Change
  one word or keep the UI label verbatim: `取消勾选 Selected Wireframe`.

Also prefer the verbs practitioners actually speak — `切一刀`, `拉出一条边`, `把点拨一下`
— over bookish variants (`进行切割`, `执行边的拉出`). Reading each finished batch aloud
in your head is the cheapest full-coverage naturalness check there is.

### Streaming-platform variant

If the user wants Netflix-compliant subtitles, their Simplified Chinese guide differs from
the house style above: commas and full stops are dropped entirely and replaced by a single
space, `、` may join list items but not end a line, italics are forbidden, quotation marks
are full-width `“”`, and work titles take `《》`. Switch only on request, and say so.

## Names and terminology, Chinese specifics

- Personal names stay in their Latin form; do not transliterate into Chinese characters
  unless the person has an established Chinese name
- On first appearance of an important concept, `中文（English）`; afterwards the short
  form alone
- Pick the wording the target audience already uses, not the literal or dictionary one.
  A technically correct term the viewer has never seen costs them a re-read, and in a
  subtitle a re-read means the demonstration on screen is gone
- "The audience's wording" means wording that reads as language, not insider slang that
  only works spoken: 大型 for *blockout* is not a word to general viewers — 基础形体
  (with Blocking bracketed at first appearance) is. See the plain-language rule in
  `references/style-common.md`

### Domain glossaries

For 3D, motion-graphics, and VFX videos — Cinema 4D, Blender, Maya, 3ds Max, Houdini,
Redshift and friends — read `references/glossary-3d-zh.md` before translating.

Its core rule is worth stating here because it decides so many lines: **one term per
concept across every 3D application, using Cinema 4D's Simplified Chinese wording**, with
an exception for features that exist in one application alone. So `Inset` in a Blender
tutorial is 内部挤压, not Blender's own 内插面; `Extrude` in a Maya tutorial is 挤压, not
挤出; `Interpolation` is 插值, never 内插; `Viewport` is 视窗, never 视口.

**But it is a table of defaults, not a substitution list.** Context outranks it: the UI
wording when the viewer must find the thing on screen, spoken Chinese when the speaker is
narrating an action, and the right sub-field sense when one English word maps to several
Chinese ones. `Create a null` is 新建一个空对象 in speech even though the menu item reads
空白; a noisy render has 噪点 while a noise shader is 噪波. Mechanical substitution
produces the same unreadable subtitle as a bad translation — it just fails consistently.

For any other domain — cooking, finance, medical — no table ships with this skill. Build
the equivalent list during the first read, following the same two principles, and hold one
rendering per concept for the whole file unless the context genuinely changes the sense.
