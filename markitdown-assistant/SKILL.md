---
name: markitdown-assistant
description: Use MarkItDown to convert user-provided files or links into clean Markdown, then optionally produce chunked JSONL for RAG ingestion. Trigger when BIGFA sends a document/file/link and asks for extraction, conversion,整理、入库前处理、markdown输出、或 chunks.jsonl 生成. For external links, default to readable relays first (defuddle.md / r.jina.ai); only fall back to MarkItDown or skill-specific routes when relays are insufficient. For X/Twitter, official X API is fallback only.
---

# MarkItDown Assistant

Use this skill to process incoming files/links into structured Markdown outputs quickly.

## Workflow

1. Confirm the input type:
   - Local file path
   - URL
   - Multiple inputs in one batch
2. If the source is a URL, first try readable relays:
   - `https://defuddle.md/<URL>`
   - `https://r.jina.ai/http://...`
3. If relay output is already sufficient, return that result directly or continue with downstream cleaning only when needed.
4. If relay output is insufficient, run the helper script:
   - `python skills/markitdown-assistant/run_markitdown.py <source...> --out-dir <dir>`
5. If user needs RAG ingest output, add `--chunks` to generate `chunks.jsonl`.
6. Return:
   - Output file paths
   - Short quality notes (OCR/table quality caveats when relevant)
   - Next-step suggestion (cleaning/indexing if needed)

## Commands

- Basic conversion:
  - `python skills/markitdown-assistant/run_markitdown.py <source> --out-dir output/markitdown`
- Batch conversion:
  - `python skills/markitdown-assistant/run_markitdown.py <s1> <s2> <s3> --out-dir output/markitdown`
- Conversion + chunking:
  - `python skills/markitdown-assistant/run_markitdown.py <source...> --out-dir output/markitdown --chunks`

## Output Contract

Always provide these artifacts when available:
- `<name>.md` for each input
- `chunks.jsonl` when `--chunks` is enabled
- `summary.json` for quick auditing

## Guardrails

- Treat conversion quality as input-dependent; explicitly flag low-confidence OCR/table results.
- Do not claim perfect semantic preservation for scanned PDFs or complex spreadsheets.
- For X/Twitter URLs, also default to readable relays first (`defuddle.md` / `r.jina.ai`); only when those fail, content is missing, or higher-confidence verification is needed, downgrade to X-specific routes. Official X API is fallback/review only.
