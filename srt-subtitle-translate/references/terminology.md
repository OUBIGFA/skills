# Subtitle Translation Reference

Use this file only when terminology consistency or edge-case formatting matters.

## Terminology Policy

- Keep English person names as written in the source unless the project already uses an established Chinese form.
- Preserve software names, product names, feature names, abbreviations, and UI labels in English when Chinese translation would be ambiguous.
- Use `中文（English）` only when first-use clarification is genuinely helpful.
- Build a temporary project glossary from the current subtitle file instead of relying on fixed domain mappings.

## Subtitle-Specific Constraints

- Do not output Markdown block quotes or citation markers.
- Do not append Chinese sentence-final punctuation to translated subtitle lines by default.
- Do not use emoji.
- Keep the output concise enough for subtitle reading speed.

## Noise Reduction Heuristics

Usually remove or compress these when they are merely filler:

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
