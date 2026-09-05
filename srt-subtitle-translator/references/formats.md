# Format Reference — SRT, WebVTT, ASS/SSA

Only dialogue wording may change. Timestamps, format structure, metadata, identifiers,
settings, non-text event fields, and protected markup are part of the file contract.
`scripts/check_subtitle.py` checks this contract when `--source` is supplied.

## SRT

- Keep the `HH:MM:SS,mmm` timestamp shape and use UTF-8 for the output.
- Renumber indices sequentially from 1 only when ordinary-mode boundaries change.
- Preserve formatting and positioning tags such as `<i>`, `<b>`, `<font>`, and `{an8}`.
- Keep one subtitle line unless the user requests bilingual or multi-speaker output.

In strict mode, the number, order, index, timestamp line, and protected markup of every
block must match the source. Only the dialogue wording can differ.

## WebVTT

Preserve exactly after normalizing line endings:

- the `WEBVTT` header and its metadata;
- every `NOTE`, `STYLE`, and `REGION` block;
- cue identifiers and cue settings such as `position:50% align:center`;
- HTML/VTT tags, ruby, karaoke timestamps, and escaped entities.

Ordinary mode may merge or split cues inside a continuous source span. A merged cue
keeps the first cue's identifier and settings; if settings differ, retain the first and
report the choice. Do not duplicate a cue identifier. Karaoke-timed text cannot safely
be translated word by word; flag it for a separate timing-aware treatment.

VTT timestamps use a dot before milliseconds and may omit the hour. Keep the source
shape. `NOTE`/`STYLE`/`REGION` blocks are not subtitle cues and do not count as blocks.

## ASS/SSA

Parse the `[Events]` `Format:` line to locate fields; the Text field can contain commas.
Modify only the Text field of `Dialogue:` events. Preserve:

- all sections, section order, script metadata, styles, and field layout;
- `Comment:`, `Picture:`, `Sound:`, and other non-Dialogue events;
- Layer, Start, End, Style, Name, margins, Effect, and every other non-Text field;
- override tags such as `{\pos(...)}`, `{\k...}`, colors, fades, and existing `\N`,
  `\n`, and `\h` markers.

Do not add line breaks. Do not merge a sign/effect event with dialogue. Overlap between
layered ASS events is allowed and is reported as a warning rather than an error.
Strict mode compares each event's non-Text fields and timestamp line exactly.

## Timing-less input

A transcript without timestamps is not a subtitle file. Translate its paragraphs in the
same shape and state that no timeline work was possible.

## Explicit conversion only

Explain losses before conversion:

- VTT → SRT loses cue settings, NOTE/STYLE/REGION blocks, and may lose cue identifiers.
- ASS/SSA → SRT/VTT loses styles, positioning, layer information, karaoke timing, and
  override tags; `\N` becomes a real line break and needs re-auditing.
- After conversion, `--source` comparison across formats is not valid. Validate the
  converted file independently and report the loss.
