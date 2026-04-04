# Chunk Workflow

Use `chunk_srt.py` when the subtitle file is too large to translate reliably in one pass.

Before translating a large or terminology-heavy subtitle, do one full-file consistency pass first. The simplest workflow is:

```bash
python scripts/extract_subtitle_terms.py "D:\Data\Desktop\demo.srt"
```

This creates a temporary sibling file such as `demo.terms.json` with recurring candidate names and terms. Use it as a working glossary while translating, then delete it after the final subtitle is merged unless the user wants to keep it.

When chunking is required, the expected workflow is to keep going until all `*.translated.srt` files are created and the final merged `-CN` file is written. Do not stop only to ask whether chunk-by-chunk continuation is acceptable.

## Split

```bash
python scripts/chunk_srt.py split "D:\Data\Desktop\demo.srt"
```

This creates a sibling chunk folder such as `demo.chunks\` containing:

- `manifest.json`
- `001.source.srt`
- `002.source.srt`
- `...`

Translate each `*.source.srt` into the matching `*.translated.srt` file while preserving block count, timestamps, and local cue order.
If the full job spans multiple replies, resume from the first missing `*.translated.srt` instead of restarting completed chunks.

## Merge

```bash
python scripts/chunk_srt.py merge "D:\Data\Desktop\demo.chunks\manifest.json"
```

This validates block counts for every translated chunk and writes the merged final subtitle beside the source file as `demo-CN.srt`.
