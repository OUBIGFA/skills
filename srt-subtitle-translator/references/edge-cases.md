# Edge Cases and Delivery

## Long files

For roughly 60 blocks or fewer, inline output is acceptable. Above that, write the
translation beside the source using the original extension. Use `source-zh.srt` for
Simplified Chinese, `source-zh-hant.srt` for Traditional Chinese, `source.en.srt` for
English, and `.bi.` for bilingual output.

When the translation is built in parts, use the local tool:

```text
python scripts/assemble_subtitle.py output.srt parts\part1.srt parts\part2.srt
```

The tool writes UTF-8, keeps SRT blocks intact, emits one VTT header, and keeps the
first ASS part's document header before adding later event lines. Validate the assembled
file before cleaning the parts.

## Cleanup on Windows

Only recycle temporary files and folders created during the current task. Never touch a
pre-existing scratch file. After the delivered output exists and the checker reports no
errors, use the recycle bin rather than permanent deletion:

```powershell
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
  '<absolute-file-path>', 'OnlyErrorDialogs', 'SendToRecycleBin')
```

For a directory, use `DeleteDirectory` with the same final two arguments. Do not use
`rm`, `del`, or `Remove-Item`. If validation fails, keep the parts so the translation can
be corrected and assembled again.

## Encoding

Read sources defensively as UTF-8, UTF-8 BOM, GB18030, or UTF-16. Always write the
delivered subtitle as UTF-8. The checker accepts legacy source encodings but requires
the output to be UTF-8. Console output may use a legacy code page; inspect the file or
use the checker rather than trusting terminal glyphs.

If the source itself contains mojibake, report it and do not pretend that it was
recovered. Do not silently repair unknown corruption.

## Timing anomalies

| Symptom | Handling |
|---|---|
| Overlap | Report it; do not invent timestamps. ASS layered events may overlap. |
| Zero or reversed duration | Preserve and flag the source anomaly. |
| Source gap | Keep it; never stretch a cue to fill silence. |
| Dense block | Remove padding, condense payload, then split at a natural target-language seam. |
| New output gap | Reject it unless it matches a source gap inside the same continuous span. |

The checker uses one configurable subtitle-gap threshold as a pause proxy. It cannot
prove an audible pause without the audio.

## Markup and speakers

Keep formatting, positioning, voice/class, ruby, karaoke, and ASS override markers with
the text they affect. Keep escaped entities escaped. Translate the word in a bracketed
sound cue when appropriate (`[music]` → `[音乐]`) but retain the bracket shape and `♪`.

Keep each dash-prefixed speaker line on its own line. Keep structural speaker labels;
their colon is not a segmentation signal. Use `--max-lines 2` for multi-speaker output.

## Bilingual output

Only produce bilingual subtitles when requested. Put the target language first and the
source second in the same block, with no blank line between them. Because the reading
load doubles, keep the translated line shorter and validate with `--max-lines 2`.

## Reporting

Report the output path, ordinary or strict mode, block count before and after, concrete
repair categories, unresolved ASR/timing/terminology issues, the checker result, and a
brief statement that self-created intermediates were recycled. Do not put notes or
explanations inside subtitle text.
