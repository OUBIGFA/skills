# Format Reference — SRT, WebVTT, ASS/SSA

The rule behind everything here: **only the dialogue text is yours; everything else is
structure and must survive byte-for-byte.** The output format is always the input format.
Converting between formats loses information (cue settings, styles, positioning) and
happens only on an explicit user request, with the losses stated.

`scripts/check_subtitle.py` parses all three formats and verifies the timeline claims;
pass `--format` only when the file extension lies.

## SRT

The baseline format; the rules in `SKILL.md` are written against it.

- Block = index line, timestamp line, text line(s), blank-line separator
- Timestamps `HH:MM:SS,mmm` with a **comma** before the milliseconds
- CRLF line endings in the source are common; write `\n` and stay consistent
- Formatting tags `<i> <b> <u> <font>` and positioning tags like `{\an8}` pass through
  around/before the translated span (see `references/edge-cases.md`)
- When boundaries change: renumber sequentially from 1

## WebVTT (.vtt)

Superset of SRT in spirit; the differences are exactly the things easiest to destroy.

Preserve unchanged:

- The `WEBVTT` header line, including anything after it on the same line, plus any
  header metadata lines before the first blank line
- `NOTE` blocks (comments), `STYLE` blocks (CSS), `REGION` definitions — never translate
  their contents
- **Cue identifiers**: the optional line above a timestamp. Keep each cue's identifier
  exactly as it was; when merging, a merged cue keeps the first cue's identifier,
  and purely numeric identifiers may be renumbered sequentially like SRT indices
- **Cue settings** after the timestamps (`position:50% line:0 align:center`): copy them
  with their timestamp line. When merging cues whose settings differ, keep the first
  cue's settings and mention it in the report
- Inline tags: voice `<v Name>`, class `<c.classname>`, ruby, and karaoke timestamps
  `<00:01:02.500>` wrap or punctuate the text — keep them positioned around the
  equivalent translated span. Karaoke-timed text is sung/timed per word; translating it
  breaks the timing, so flag it instead of translating word-by-word timing

Differences from SRT:

- Timestamps use a **dot** before the milliseconds (`00:01:02.500`), and the hour part is
  optional — do not add or remove the hour field; write times in the same shape the
  source used
- Text may legally contain `-->`-free blank-line-separated blocks that are not cues
  (NOTE/STYLE); do not count them as subtitle blocks
- Escapes `&amp; &lt; &gt;` stay escaped

## ASS/SSA (.ass, .ssa)

A whole document, not a list of blocks. Sections: `[Script Info]`, `[V4+ Styles]`
(or `[V4 Styles]` for SSA), `[Events]`, sometimes `[Fonts]`/`[Graphics]`.

Touch **only the Text field of `Dialogue:` lines in `[Events]`**. Everything else —
script info, resolution, styles, `Comment:` events, field order — is copied verbatim.

- The `Format:` line in `[Events]` defines the field order; `Text` is last and may itself
  contain commas, so split on at most `len(fields)-1` commas
- Timestamps `H:MM:SS.cc` — **centiseconds**, single-digit hour. Same shape out as in
- Override tags `{\...}` (position, color, karaoke, fades) stay exactly where they are
  relative to the text they affect. `{\k...}` karaoke tags time individual syllables —
  translating karaoke lines word-by-word breaks them; flag instead
- `\N` (hard) and `\n` (soft) line breaks: existing ones stay; **adding one is wrapping**
  and is not allowed. `\h` is a hard space — keep it
- Style names referenced by Dialogue lines must not be renamed
- Overlapping events are often intentional (a positioned sign over dialogue, layered
  effects) — the checker reports overlap as a warning for ASS, not an error. Do not
  "fix" it
- Boundary changes: merge only Dialogue events that share the same Style and Layer; a
  merged event spans the first start and last end, keeps the first event's other fields.
  Never merge a sign/effect event with dialogue

## Timing-less input

A plain transcript with no timestamps is not a subtitle file. Translate the text, return
the same shape (paragraphs in, paragraphs out), and say that no timeline work was
possible.

## Conversion (explicit request only)

State the losses before doing it: SRT cannot hold VTT cue settings, NOTE/STYLE blocks, or
ASS styles/positioning/karaoke — that styling disappears. VTT→SRT: dots become commas,
cue identifiers and settings drop. ASS→SRT/VTT: override tags drop, `\N` becomes a real
line break (which then violates one-block-one-line — re-audit those blocks). After
converting, `--source` verification no longer applies across the boundary; verify the
converted file on its own and say so in the report.
