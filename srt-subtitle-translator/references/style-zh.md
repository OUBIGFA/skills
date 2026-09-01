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
  abbreviations, and English UI labels: `在 C4D 中设置 100%，亮度为 500nits`
- **中文词汇严禁前后留空格**：空格仅用于中英文/数字分界或意群间停顿，中文词汇之间绝不可因属于专有名词或 UI 术语而生硬留出前后空格（错误：`但 吸引 完全没有任何可视反馈`、`摩擦 还在 我先把 摩擦 关掉`）。此类词汇要么取消前后空格自然融入中文句式（`但吸引完全没有任何可视反馈`、`摩擦还在 我先把摩擦关掉`），要么直接保留英文原文并按中英混排规则留空格（建议保留英文原文：`但 Attractor 完全没有任何可视反馈`、`Friction 还在 我先把 Friction 关掉`）。
- No space between a number and its unit symbol, and no space around punctuation
- Use full-width Chinese punctuation inside the line. `，、？` are normal when the
  sentence needs them; use `：` only for a genuine explanation, label, or structural
  introduction. Exclamation marks (`！` and `!`) are strictly forbidden across all
  subtitles — never use exclamation marks in subtitle translation; express enthusiasm or
  urgency through natural vocabulary, or convert to plain declarative sentences.
  A translation-created `；` normally calls for a block split instead.
  Use half-width numerals (`1, 2, 3`, never `１２３`).

Wrong: `在C4D中设置100%,亮度为500nits`

## Single-thought blocks and segmentation marks

One Chinese subtitle block carries one complete thought. An internal full stop `。` or
semicolon `；` is a strong signal that the line contains two completed or separately
divided thought units. Split those units into separate blocks at a natural Chinese
boundary and distribute them across the speech span.

This is not a general punctuation ban. Commas `，`, enumeration commas `、`, and
question marks `？` are normal within one thought and do not justify a split by themselves.
(Exclamation marks `！`/`!` are forbidden throughout and must not appear in any block.)
A colon `：` is valid when a genuine explanation, label, or structural introduction needs
it; otherwise prefer a natural rewrite. Meaning decides the boundary, but internal `。`
and `；`, as well as any exclamation marks `！`/`!`, receive automatic mechanical warnings.

Structural speaker labels, UI labels, menu paths, code, and strings the viewer sees typed
are exceptions and remain faithful to the source. A punctuation mark that belongs to
such a string is not a translation-created segmentation mark.

Examples:

- `首先选择对象；然后打开 Settings 面板` → split into `先选择对象` / `再打开 Settings 面板`
- `原因很简单：我们需要更多几何体` → keep the colon when the explanation reads as one thought
- `选择对象。然后打开面板` → split into two blocks rather than keeping an internal `。`
- `先选择对象，再打开面板` → keep the comma when it remains one thought (no exclamation mark)
- `位置、旋转和缩放都能调整` → keep the enumeration comma
- `John：请打开面板` keeps the structural speaker label

## Punctuation at line ends

Subtitles are timed, not typeset — the cut in time already ends the thought, so a trailing
full stop adds a character and no information. Do not end a subtitle text line with
`。．.` `;；` `:：` `，,` `、` `！!`. A genuine question may end with `？`; this mark
carries question tone and is not treated like a full stop.

Exclamation marks (`！` and `!`) are completely banned from subtitles, both at line ends
and within lines. Even if the speaker sounds excited or urgent, translate using natural
spoken vocabulary without adding exclamation marks.

Punctuation inside a line is not a substitute for a subtitle boundary. Split when the
meaning contains two thought units, especially when `。` or `；` makes the separation
explicit. Do not split merely because a normal comma, enumeration comma, or question mark
appears.

A sentence that runs into the next block gets no ellipsis, no dash, no trailing comma —
the timeline carries the continuation. Reserve `⋯`(U+2026) for a pause of two seconds or
more, or an interruption.

Use full-width `？` for genuine questions when their tone matters. Never use `！` or `!`.

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
