# Subtitle Translation Reference

Use this file only when terminology consistency or edge-case formatting matters.

## Non-Translatable Or Usually Kept In English

- Cinema
- Noise
- Redshift
- Volume
- Fields
- Beauty
- Coloso
- Bucket Rendering

## Preferred Mappings

- Plane -> 平面
- Material -> 材质
- Light -> 灯光
- Lighting -> 布光
- Displacement -> 置换
- Mask -> 遮罩
- Commander -> 管理器
- Viewport -> 视窗
- Example -> 案例

## Terminology Policy

- Keep English person names as written in the source.
- Transliterate non-English person names into a stable English-form spelling when needed by the source convention.
- Preserve software names, feature names, and abbreviations in English if Chinese translation would be ambiguous.
- Use `中文（English）` only when first-use clarification is helpful.

## Subtitle-Specific Constraints

- Do not output Markdown block quotes or citation markers.
- Do not append `。` to the end of translated subtitle lines by default.
- Do not use emoji.
- Keep the output concise enough for subtitle reading speed.

## Noise Reduction Heuristics

Usually remove or compress these when they are merely filler:

- 嗯
- 哦
- 呃
- 这个
- 那个
- 实际上
- 就是说
- Yeah
- OK
- Ok
- Nice
- Cool
- Uh
- Um
- Like
- You know
- Sort of
- I mean

Keep them only if they function as real content, such as:

- `Click OK` -> `点击确定`
- `keep it cool` -> `保持冷却`

## Symbol And Formatting Reminders

- `Negative 50` -> `-50`
- `360 degrees` -> `360°`
- `20 percent` -> `20%`
- `10 by 10` -> `10×10`
- `from 10 to 20` -> `10~20`
- `plus or minus 5` -> `±5`
- `在 C4D 中设置 100%，亮度为 500nits`
