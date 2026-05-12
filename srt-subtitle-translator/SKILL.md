---
name: srt-subtitle-translator
description: Optimize and translate SRT subtitle files into clean Chinese. Always first read the full subtitle, build a terminology table, semantically re-segment non-Chinese subtitles into a human-edited optimized SRT, then translate the optimized SRT while preserving its numbering and timestamps exactly. Use this skill whenever the user asks to translate subtitles, localize SRT files, clean ASR subtitles, translate tutorial captions, produce Chinese .srt output, or handle Cinema 4D/3D/rendering tutorial subtitles, even if they only say "翻译这份字幕" or mention an .srt file.
version: 1.0.0
---

# SRT Subtitle Translator

Use this skill to optimize and translate `.srt` subtitles into concise, professional Chinese. The main goal is readable subtitles, not word-for-word transcription. First create a semantically optimized source subtitle with better human sentence breaks, then translate that optimized version while cleaning noisy spoken language and standardizing symbols, units, terminology, and Chinese-English typography.

## Core Tasks

1. Maintain complete SRT structure
2. Read the full subtitle before translating and build a terminology table
3. Semantically optimize subtitle segmentation before translation
4. Clean spoken-language noise and ASR artifacts
5. Symbolize numbers, angles, ranges, and logic expressions
6. Standardize Chinese-English mixed typography
7. Preserve domain terminology for 3D, rendering, software UI, and technical tutorials

## Required Workflow

1. Inspect the input file
   - Confirm it is SRT-like: numeric index, timestamp line, subtitle text, blank separator
   - Count total lines and subtitle blocks
   - Note encoding if obvious

2. Read the full subtitle before translating
   - Understand topic, speaker habits, repeated UI terms, repeated verbs, and domain context
   - Identify ASR errors that can only be corrected with global context
   - Create a working terminology table before producing the final translation
   - Keep terminology and repeated expressions consistent across the whole file

3. Create the optimized source subtitle
   - Re-segment subtitle text semantically before translation
   - Apply human sentence breaks so each subtitle block contains a complete or natural phrase
   - This applies to all non-Chinese subtitle sources, not only English
   - Merge or split subtitle text when ASR line breaks cut through a phrase, clause, object name, or technical term
   - Adjust timestamps when needed so the optimized subtitle remains readable and timed to speech
   - Save this file in the source subtitle directory as `<原文件夹名>_Optimize.srt`

4. Translate from the optimized subtitle
   - Treat the optimized file as the structural source for translation
   - Keep optimized subtitle indices unchanged
   - Keep optimized timestamp lines unchanged
   - Keep optimized blank separator lines unchanged
   - Clean and compress meaning while preserving actual operations, parameter values, UI labels, software names, and causal explanations
   - Save the final Chinese subtitle in the source subtitle directory as `<原文件夹名>_Optimize_CN.srt`

5. Clean up intermediate artifacts
   - Deliver only the optimized source subtitle and final Chinese subtitle
   - Remove temporary scripts, scratch files, temporary terminology files, chunk files, and partial outputs after successful completion
   - Do not remove the original subtitle or the two delivered files

6. Verify output
   - Optimized source subtitle is valid SRT
   - Final Chinese subtitle has the same indices, timestamps, and block count as the optimized subtitle
   - Every timestamp line in the final Chinese subtitle matches the optimized subtitle exactly
   - Report both output paths and verification result

## Structural Integrity Rules

These rules have two stages:

Optimization stage:

- The original subtitle may be semantically re-segmented to improve translation quality and Chinese readability
- Adjacent blocks may be merged when a sentence, technical phrase, UI label, or object name is broken across blocks
- Long blocks may be split at natural semantic boundaries such as cause, contrast, result, or operation steps
- Timestamps may be adjusted when necessary, but keep chronological order, non-overlap, and realistic timing
- Renumber the optimized subtitle sequentially if merging or splitting changes the block structure
- Do not drop substantive information during optimization

Translation stage:

- The final Chinese subtitle must exactly match the optimized subtitle's indices
- The final Chinese subtitle must exactly preserve the optimized subtitle's timestamps
- Do not merge, split, renumber, or retime while translating from the optimized subtitle
- If ASR content is illogical, correct the meaning using global context, but keep it in the corresponding optimized block
- If a block is too short or too broken to infer confidently, translate the optimized source directly and keep it readable

## Semantic Segmentation Rules

The optimized subtitle exists to make translation natural and coherent. Do this before translating, especially for ASR subtitles.

Merge when a subtitle break interrupts:

- A noun phrase or technical term
- A software command or UI path
- A verb-object phrase
- A short clause that depends on the next block
- A sentence that clearly continues into the next timestamp

Split when a subtitle block contains:

- Two independent operations
- A cause-and-effect boundary
- A contrast such as `but`, `however`, `because`, `so`
- A very long subtitle that would create an overloaded Chinese line

Examples:

Input:

```srt
12
00:00:28,740 --> 00:00:35,320
I just selected those edges and stored those selections to bevel them out only with that

13
00:00:35,320 --> 00:00:36,385
bevel deformer.
```

Optimized:

```srt
12
00:00:28,740 --> 00:00:36,385
I just selected those edges and stored those selections to bevel them out only with that bevel deformer
```

Input:

```srt
23
00:01:10,160 --> 00:01:14,960
And as you can see, the result is far from what it is supposed to look like because we

24
00:01:14,960 --> 00:01:19,440
don't have right now the supporting edges to support those sharp edges.
```

Optimized:

```srt
23
00:01:10,160 --> 00:01:14,860
As you can see, the result is far from what it is supposed to look like

24
00:01:14,860 --> 00:01:19,440
because we don't have the supporting edges for those sharp edges
```

## Noise Filtering

Priority: highest.

Strongly filter meaningless spoken-language noise. Subtitles should communicate the operation or meaning, not every hesitation.

Remove when used as filler, hesitation, or agreement:

- 中文: 嗯, 哦, 呃, 这个, 那个, 实际上, 就是说
- English: Yeah, OK, Ok, Okay, Nice, Cool, Uh, Um, Like, You know, Sort of, I mean

Keep only when the word carries actual meaning:

- `keep it cool` -> `保持低温` or `冷却`
- `Click OK` -> `点击 OK` or `点击确定`
- `OK button` -> `OK 按钮`

For fragmented self-talk, condense aggressively:

- `Cool, let's check this, yeah, maybe this is okay` -> `我们来检查一下，这样基本可以`
- `I mean, like, maybe just move this over here` -> `可以把它移到这里`

Do not remove operational content, values, object names, or visual judgments that guide the tutorial.

## Terminology Table Before Translation

Before translating, build a working terminology table from the full subtitle. This table can be kept as an internal working artifact and should be cleaned up after delivery unless the user asks to keep it.

Include:

- Software names
- UI labels and menu paths
- Object names
- Modifier, shader, renderer, and algorithm names
- Repeated verbs or expressions that need consistent Chinese rendering
- ASR correction decisions

Use the terminology table to keep the entire file consistent. If a term appears multiple ways because of ASR errors, normalize it to one chosen form in the optimized subtitle and final translation.

## Symbolization Rules

Priority: highest.

Use professional symbols to improve subtitle reading speed:

- Negative numbers: keep the mathematical sign, do not write Chinese words
  - `Negative 50` -> `-50`
- Angles: use degree symbol
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

Prefer Arabic numerals over Chinese numerals for settings, counts, steps, frames, and UI values.

## Unit Standardization

Use SI and common technical unit symbols. Do not translate unit names into Chinese full names.

- `50 kilograms` -> `50kg`
- `100 meters` -> `100m`
- `220 volts` -> `220V`
- `50 hertz` -> `50Hz`
- `500 nits` -> `500nits`

Do not add a space between a number and its unit symbol.

## Chinese-English Typography

Follow Pangu spacing:

- Add one half-width space between Chinese text and English words
- Add one half-width space between Chinese text and numbers
- Do not add a space between numbers and unit symbols
- Keep punctuation in Chinese style unless preserving a UI label

Correct:

- `在 C4D 中设置 100%，亮度为 500nits`
- `把 Volume Builder 的 Voxel Size 调到 0.3`
- `使用 Redshift Render View 预览`

Wrong:

- `在C4D中设置100%,亮度为500nits`
- `把Volume Builder的Voxel Size调到0.3`

## Subtitle-Specific Formatting

- Do not add full stops or other ending punctuation at the end of translated subtitle lines
- Do not use emoji
- Never output `[cite]`, `[]`, citation markers, footnotes, or source markers inside subtitles
- Preserve English personal names
- Transliterate non-English personal names into English form if needed
- Keep UI labels in English when exact software operation matters
- For UI labels that benefit from clarity, use `中文（English）` on first or important occurrence

Ending punctuation ban applies to subtitle text lines. Commas and pauses inside a line are allowed when needed for readability, but avoid heavy punctuation.

## Terminology Handling

For software names, renderer names, algorithms, UI labels, and abbreviations:

- Preserve the English term if translating it may create ambiguity
- Use `中文（English）` when a Chinese explanation helps
- Prefer established CG/C4D terminology
- Do not force-translate UI labels that users need to locate in software

Use the bundled terminology reference when translating C4D, Redshift, 3D, rendering, or tutorial subtitles:

- `references/c4d-rendering-terms.md`

## Built-In Terminology Rules

Do not translate these terms unless context clearly demands explanation:

- Cinema
- Noise
- Map
- Ramp
- Planar
- Redshift
- Volume
- Fields
- Beauty
- Coloso
- Bucket Rendering

Compulsory mappings:

- `Okay` as filler -> remove; as UI label -> `OK`
- `Plane` -> `平面`
- `Material` -> `材质`
- `Light` -> `灯光` when object/source; use context for adjective senses
- `Lighting` -> `布光` when referring to lighting setup
- `Displacement` -> `置换`
- `Mask` -> `遮罩`
- `Commander` -> `管理器`
- `Viewport` -> `视窗`, not `视口`
- `Example` -> `案例`, not `示例`, when referring to a worked example or demo result

## ASR Correction Guidelines

When subtitles come from speech recognition:

- Correct obvious domain misrecognitions using global context
- Preserve the intended tutorial operation rather than the literal mistaken word
- Do not stop the task because one line is odd
- If a short timestamp contains an unusually long sentence, translate it directly and concisely
- Do not invent missing technical steps

Examples:

- `cam model` in a pouring soda tutorial likely means `can model` -> `易拉罐模型`
- `negative wire` in a C4D transform context likely means `negative Y` -> `负 Y`
- `cool sticks` in Redshift render settings likely means `Caustics` -> `Caustics`

## Output Quality Checklist

Before final response, verify:

- `<原文件夹名>_Optimize.srt` exists in the original subtitle directory
- `<原文件夹名>_Optimize_CN.srt` exists in the original subtitle directory
- Optimized subtitle is valid SRT
- Final Chinese subtitle indices exactly match the optimized subtitle
- Final Chinese subtitle timestamp lines exactly match the optimized subtitle
- Optimized subtitle and final Chinese subtitle block counts match
- No subtitle text line ends with `。`, `.`, `！`, `!`, `？`, or `?`
- No citation markers are present
- Chinese-English spacing is applied
- Numbers, units, angles, percentages, and ranges use standardized symbols
- Technical terms are consistent
- Filler words are removed unless semantically required
- Temporary scripts, scratch files, chunk files, temporary terminology files, and partial outputs have been removed

## Final Response

Keep the final response brief. Include:

- Optimized source subtitle path
- Final Chinese subtitle path
- Verification summary: optimized/final block count match, final timestamp preservation against optimized file, cleanup complete
- Any important caveat, such as uncertain ASR corrections

Do not paste the whole subtitle content unless the user explicitly asks.
