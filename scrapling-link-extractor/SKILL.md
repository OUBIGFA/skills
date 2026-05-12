---
name: scrapling-link-extractor
description: Use this skill whenever the user sends one or more web links and wants the page content extracted, saved, cleaned up, summarized, archived, converted to Markdown/JSON, or prepared for later use. This should trigger automatically for requests like "grab this page", "extract this article", "save this X post", "整理这篇文章", "抓一下这个网页", or a bare URL plus an action. Prefer readable relay routes first (`defuddle.md`, `r.jina.ai`), then fall back to Scrapling when the relays fail or content is incomplete. X/Twitter links also use this route first; do not wait for the user to explicitly name the skill.
description_zh: 当用户发送一个或多个网页链接，并希望抓正文、提取内容、保存文章、整理链接、转成 Markdown/JSON、做摘要、入库或归档时，必须优先使用这个 skill。对“把这篇文章保存下来”“抓一下这个网页”“提取这条 X 帖子”“整理这个链接内容”以及“URL + 动词”的请求，应自动触发；不要等用户点名 `scrapling-link-extractor`。
version: 1.1.0
---

# Scrapling Link Extractor

Turn user-supplied URLs into usable article/page content with predictable outputs:

- `*.md` for readable text
- `*.json` for structured extraction
- `summary.json` for multi-link runs

## Trigger Rules

Use this skill by default when any of these are true:

- The user sends a URL and asks to:
  - extract
  - scrape
  - save
  - archive
  -整理
  -提取
  -抓取
  -转成 Markdown
  -summarize after fetching
- The user sends mostly links with little other context, and the intent is clearly "get the content out".
- The target is an article, blog post, documentation page, X/Twitter post, forum thread, newsletter, public note, or other readable webpage.
- The user wants the content stored locally for later use.

This skill should also trigger for common phrasings like:

- "把这篇文章保存到桌面"
- "抓一下这个网页正文"
- "提取这个链接里的内容"
- "Save this post as markdown"
- "Archive this X thread"
- "帮我整理这几个网页"

Do not require the user to explicitly say `scrapling-link-extractor`.

## When Not To Use It

Do not use this as the first tool when the user mainly wants:

- broad discovery across the web: use `web-search`
- interactive browsing, login, clicking, or screenshots: use `browser-use`
- only a quick fact lookup from a page the model already has in context

If the request starts from a concrete URL and the goal is to extract page content, this skill has priority over `web-search`.

## Default Route

For each URL:

1. Identify the input URL(s).
2. Try readable relay path 1:
   - `https://defuddle.md/<URL>`
3. Try readable relay path 2:
   - `https://r.jina.ai/http://...`
4. If one relay returns enough clean content, use that result directly.
5. If both relays fail, are blocked, or clearly lose important content, fall back to Scrapling.
6. For X/Twitter links, use the same two relay paths first. Only use an X-specific route as fallback or for verification.

## Practical Heuristic

If the user message matches either of these patterns, trigger this skill automatically:

- `URL` + action verb
- one or more `URL`s with an implied content-handling intent

Examples:

- `https://x.com/... 把这篇文章保存到桌面`
- `https://example.com/post/123 提取正文`
- `帮我把这三个链接整理成 md`

## Scrapling Fallback Command

Prefer portable paths and existing local files:

```powershell
python "$SKILLS_ROOT/scrapling-link-extractor/run_scrapling_extract.py" `
  "<URL1>" "<URL2>" `
  --out-dir "D:\Software\scrapling-bot\output"
```

If the environment requires a specific interpreter, resolve it first, but keep the skill behavior the same.

## Output Contract

For each URL, produce:

- `<slug>.md`
- `<slug>.json`

And one run summary:

- `summary.json`

When reporting back to the user, include:

- whether extraction succeeded
- where the files were saved
- whether the result came from relay content or Scrapling fallback
- any known lossiness or blockers

## Failure Handling

When extraction fails, state the reason concretely:

- timeout
- 403 / 503 / anti-bot wall
- login required
- certificate / SSL issue
- relay returned empty or partial content

Then continue to the next sensible fallback instead of stopping early.

## Notes

- Only promise successful extraction when files were actually produced.
- Public content first; authenticated pages may still fail.
- For X/Twitter, do not start with official API assumptions. Relay-first is the default path.
- If the user asks to save the result locally, complete the save as part of the same workflow.
