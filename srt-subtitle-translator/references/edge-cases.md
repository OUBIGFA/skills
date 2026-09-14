# Edge Cases and Delivery

## Long files

For roughly 60 blocks or fewer, inline output is acceptable. Above that, write the
translation beside the source using the original extension. Use `source-zh.srt` for
Simplified Chinese, `source-zh-hant.srt` for Traditional Chinese, `source-en.srt` for
English, and `source-bi.srt` for bilingual output.

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
be corrected and assembled again. Before replying to the user, recycle the task
workspace and all intermediate artifacts, including artifacts from failed validation.

If the sandbox blocks `Add-Type` ("compiles and loads .NET code at runtime") and COM
instantiation, the equivalent recycle call is available through Python's `ctypes`:

```python
import ctypes, sys
class OP(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
op = OP(); op.wFunc = 3                      # FO_DELETE
op.pFrom = "\0".join(sys.argv[1:]) + "\0\0"  # double-null terminated list
op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO|NOCONFIRMATION|SILENT|NOERRORUI
ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
```

Pass every path in one call (recursing into a directory is not automatic; `FO_DELETE` on
a directory does remove its contents). Verify with `os.path.exists` that each target is
gone, and only if that still fails report the remaining paths instead of claiming success.

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
