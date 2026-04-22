# Subtitle Translation Helper Scripts

These scripts only preprocess, scan, split, validate, and merge subtitle files. The language model in the main conversation does the actual semantic segmentation review, translation, and final review/polish.

Entry points:

- `preprocess_srt.py` - whitespace/formatting normalization; never rewrites cue boundaries. Default output is `<stem>.preprocessed<ext>` beside the source; `-CN` is reserved for the formal final deliverable.
- `extract_subtitle_terms.py` - scan the subtitle for recurring names/terms and emit a candidate glossary JSON for translation consistency.
- `detect_orphan_tails.py` - report-only scan for suspicious orphan-tail / orphan-lead cue pairs that may deserve review during semantic segmentation.
- `detect_clause_rebalance.py` - report-only scan for possible clause-boundary rebalance candidates. The model decides whether any repair is actually warranted.
- `chunk_srt.py` - `split` a large subtitle into runtime-based chunks (default about 20 min each) and later `merge` translated chunks back into one draft subtitle; hard-fails on any cue / timestamp / block-count mismatch.
- `subtitle_pipeline.py` - orchestrator. `prepare` runs preprocess + term extract + optional hint reports, and only creates chunks when runtime exceeds about 30 min or `--force-chunk` is passed. `set-stage` persists `prepared`, `translated`, `review_polished`, or `finalized` after main-conversation work. `finalize` merges to a draft subtitle by default and writes the formal final output only when passed `--reviewed`. `clean` deletes default intermediates. `status` prints the pipeline JSON.

Typical flows:

## Full pipeline (recommended)

```bash
python scripts/subtitle_pipeline.py prepare "D:\Data\Desktop\demo.srt"
# Main model reviews segmentation, translates, and polishes.
python scripts/subtitle_pipeline.py finalize "D:\Data\Desktop\demo.pipeline.json" --reviewed
```

## Manual chunking

```bash
python scripts/extract_subtitle_terms.py "D:\Data\Desktop\demo.srt"
python scripts/chunk_srt.py split "D:\Data\Desktop\demo.srt"
# Main model translates each NNN.source.srt into NNN.translated.srt with identical cue numbers and timestamps.
python scripts/chunk_srt.py merge "D:\Data\Desktop\demo.chunks\manifest.json"
```

Optional hint reports during semantic segmentation review:

```bash
python scripts/detect_orphan_tails.py "D:\Data\Desktop\demo.srt"
python scripts/detect_clause_rebalance.py "D:\Data\Desktop\demo.srt"
```

If execution spans multiple replies, resume from the first missing `*.translated.srt` instead of restarting completed chunks. Do not use parallel subagents as the default translation path.
