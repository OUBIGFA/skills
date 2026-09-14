---
name: openai-whisper
description: 使用本地 Whisper 将音频转写为文字或字幕时使用。
description_zh: "本地语音转文字（无需 API 密钥）"
description_en: "Local speech-to-text (no API key needed)"
---

# Whisper (CLI)

Use `whisper` to transcribe audio locally.

Quick start
- `whisper /path/audio.mp3 --model medium --output_format txt --output_dir .`
- `whisper /path/audio.m4a --task translate --output_format srt`

Notes
- Models download to `~/.cache/whisper` on first run.
- Set `--output_dir` to the requested destination, or to the task's `_temp/<unique-directory>` for intermediate files. Check current CLI defaults rather than assuming an installed model.
- Use smaller models for speed, larger for accuracy.
