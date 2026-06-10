---
name: srt-subtitle-translator
description: Translate non-Chinese SRT subtitles into concise, professional Simplified Chinese by manual human-quality translation only, while preserving the original SRT numbering, timestamps, block order, and blank-line structure exactly. Never use third-party translation APIs, machine translation tools, browser translators, online translation websites, local translation software, or automated translation plugins. Always use this skill whenever the user asks to translate subtitles, clean ASR subtitle text, produce Chinese SRT output, handle tutorial captions, or mentions .srt files, subtitle translation, SRT Mode, Cinema 4D, rendering, or technical course captions.
version: 1.0.0
---

# SRT Subtitle Translator

Use this skill to translate non-Chinese `.srt` subtitles into clean, accurate, high-signal Simplified Chinese. Preserve the SRT timeline structure exactly while removing spoken-language noise, standardizing symbols and units, and keeping technical terminology consistent.

## Role

Act as a professional technical-document translator and subtitle editor with a strong science and engineering background. Prioritize fluent Chinese, accurate technical meaning, subtitle readability, and strict SRT structural integrity.

## Manual Translation Only

This skill requires manual translation by the assistant. Do not delegate translation to any external or third-party translation system.

Forbidden tools and sources:

- Third-party translation APIs
- Online translation websites
- Browser built-in translation
- Local translation applications
- Machine translation plugins
- AI translation services outside the current assistant workflow
- Batch translation scripts that call an external translation service

Allowed assistance:

- Read the source subtitle file
- Inspect surrounding subtitle context
- Use domain knowledge and reasoning to translate manually
- Use local text-processing tools only for non-translation tasks such as counting blocks, checking timestamps, validating SRT structure, comparing indices, or formatting output

If a translation tool is available, ignore it. If the user asks to use a translation API or external translator, refuse that part and proceed with manual translation unless the user changes the requirement.

## Core Tasks

1. Preserve SRT structure exactly
2. Translate non-Chinese subtitle text into Simplified Chinese
3. Perform all translation manually without third-party translation tools or APIs
4. Remove filler words, hesitation, and low-value spoken noise
5. Correct obvious ASR errors using full-context understanding
6. Standardize symbols, numbers, units, and Chinese-English typography
7. Preserve or consistently translate technical terminology
8. Output only the final translated SRT

## Required Workflow

1. Read the full SRT before translating
   - Understand the topic, domain, speaker habits, repeated UI labels, and repeated terms
   - Identify likely ASR errors from context
   - Decide terminology mappings before producing final output
   - Do not send source subtitle text to any third-party translation API, website, tool, plugin, or external service

2. Validate the SRT structure
   - Keep every original subtitle index
   - Keep every timestamp line unchanged
   - Keep block order unchanged
   - Keep blank-line separation between blocks
   - Do not merge, split, skip, renumber, or retime blocks

3. Translate each block in place
   - Translate the text belonging to each source index into the corresponding output index
   - If a source line is fragmented or noisy, condense it into readable Chinese inside the same block
   - If ASR caused obvious wording errors, correct the meaning with context while keeping the result in the same block
   - If the meaning cannot be confidently repaired, translate the original text directly and keep it readable

4. Verify before responding
   - Output indices exactly match the input indices
   - Timestamp lines are byte-for-byte unchanged
   - No input block is missing
   - No output block is added
   - No Markdown citations, explanations, comments, or notes are present
   - Subtitle text line endings do not use sentence-final punctuation

## Hard Structural Rules

These rules are mandatory.

- Output numbering must match the input numbering exactly
- Timestamp lines must remain exactly unchanged
- Do not alter any timestamp number, comma, arrow, spacing, or symbol
- Do not merge subtitle blocks
- Do not split subtitle blocks
- Do not reorder subtitle blocks
- Do not skip subtitle blocks
- Do not add extra subtitle blocks
- If ASR text is illogical, correct the meaning with context but keep it under the same index
- If a block is extremely short or malformed, still preserve the index and timestamp and provide the best readable translation

## Noise Filtering

Priority: highest.

Aggressively remove meaningless filler, hesitation, agreement, self-talk, and emotional padding. Subtitles should communicate the actual operation or meaning, not every spoken fragment.

Remove when used as filler, hesitation, or agreement:

- Chinese: 嗯, 哦, 呃, 这个, 那个, 实际上, 就是说
- English: Yeah, OK, Ok, Okay, Nice, Cool, Uh, Um, Like, You know, Sort of, I mean

Keep only when the word carries actual meaning:

- `keep it cool` -> `保持低温` or `冷却`
- `Click OK` -> `点击 OK` or `点击确定`
- `OK button` -> `OK 按钮`

For fragmented self-talk, condense rather than translating word for word:

- `Cool, let's check this, yeah, maybe this is okay` -> `我们来检查一下，这样基本可以`
- `I mean, like, maybe just move this over here` -> `可以把它移到这里`

Do not remove actual operations, parameter values, object names, visual judgments, warnings, or causal explanations.

## Symbolization Rules

Priority: highest.

Use compact professional symbols to improve subtitle reading speed:

- Negative numbers: keep mathematical signs, do not write them as Chinese words
  - `Negative 50` -> `-50`
- Angles: use degree symbols
  - `360 degrees` -> `360°`
  - `90 degrees` -> `90°`
- Percentages: use `%`
  - `20 percent` -> `20%`
- Dimensions and multiplication: use `×`
  - `10 by 10` -> `10×10`
- Logic, comparison, and ranges: use compact symbols where clear
  - `from 10 to 20` -> `10~20`
  - `greater than 5` -> `>5`
  - `less than 3` -> `<3`
  - `plus or minus 5` -> `±5`

Prefer Arabic numerals for settings, counts, frames, steps, parameter values, and UI values.

## Unit Standardization

Use SI and common technical unit symbols. Do not translate units into Chinese full names when a standard symbol is expected.

Examples:

- `50kg`, not `50千克`
- `100m`, not `100米`
- `220V`, not `220伏特`
- `50Hz`, not `50赫兹`
- `500nits`, not `500 尼特`

Do not add spaces between numbers and unit symbols.

## Chinese-English Typography

Apply Chinese-English mixed typography rules.

- Add one half-width space between Chinese text and English words
- Add one half-width space between Chinese text and Arabic numerals
- Add one half-width space between Chinese text and software names, abbreviations, and UI labels
- Do not add spaces between numbers and unit symbols
- Use Chinese punctuation inside translated subtitle text, except where subtitle punctuation rules prohibit it

Correct:

```text
在 C4D 中设置 100%，亮度为 500nits
```

Wrong:

```text
在C4D中设置100%,亮度为500nits
```

## Subtitle Punctuation Rules

- Do not end subtitle text lines with a Chinese full stop, English period, exclamation mark, question mark, semicolon, colon, or other sentence-final punctuation
- Avoid unnecessary commas at line ends
- Do not use emoji
- Do not output `[cite]`, `[]`, footnotes, source markers, or any citation markers
- Do not output explanations, translator notes, comments, or thinking process

If a line naturally requires a question or warning, preserve the meaning without sentence-final punctuation when possible.

## Names and Terminology

- Keep English personal names in English
- Romanize non-English personal names into English form when needed
- Keep software names, algorithm names, renderer names, plugin names, and acronyms in English unless a stable Chinese translation exists
- For important technical concepts, use `中文（English）` on first appearance when it improves clarity
- Do not force-translate terms in a way that creates ambiguity

Preferred domain handling:

- Preserve these terms in English when they refer to products, UI labels, render passes, or named features: `Cinema`, `Noise`, `Redshift`, `Volume`, `Fields`, `Beauty`, `Coloso`, `Bucket Rendering`
- Use these mappings when context matches:
  - `Plane` -> `平面`
  - `Material` -> `材质`
  - `Light` -> `灯光`
  - `Lighting` -> `布光`
  - `Displacement` -> `置换`
  - `Mask` -> `遮罩`
  - `Commander` -> `管理器`
  - `Viewport` -> `视窗`
  - `Example` -> `案例`

Do not translate `Viewport` as `视口` in Cinema 4D or similar tutorial contexts. Do not translate `Example` as `示例` when it means a tutorial case.

## ASR Error Handling

When speech recognition has clearly produced the wrong word:

- Use the surrounding subtitles and domain context to infer the intended meaning
- Correct the translated result naturally in Chinese
- Keep the corrected content under the original index
- Do not move corrected content into neighboring blocks
- Do not terminate or refuse just because a block contains ASR errors

For extremely short timestamps containing unusually long or garbled text, translate the original as well as possible while preserving structure.

## Output Format

Return only the final translated SRT inside one Markdown code block.

Use raw SRT structure:

```srt
1
00:00:00,000 --> 00:00:02,000
翻译后的字幕文本

2
00:00:02,000 --> 00:00:04,000
翻译后的字幕文本
```

Do not include any preface, summary, verification table, explanation, or extra text unless the user explicitly asks for it.

## Final Self-Check

Before responding, compare the output against the input:

- Same subtitle indices
- Same timestamp lines
- Same block count
- Same block order
- No changed timestamps
- No added explanations or citations
- No sentence-final punctuation on subtitle text lines
- Chinese-English spacing and unit formatting are correct
