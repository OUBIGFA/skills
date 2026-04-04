---
name: scrapling-link-extractor
description: 当 BIGFA 发送网页链接并要求“爬取/提取/抓内容/整理正文”时触发。默认先走可读中转双路（defuddle.md / r.jina.ai）；两路抓不到或内容明显缺失时，再用 Scrapling 补抓。X/Twitter 也先走这套双路，官方 X API 只作备用。
---

# Scrapling Link Extractor

把用户给的网页链接快速转成可用内容，默认输出：
- `*.md`（可读正文）
- `*.json`（结构化结果）

## 何时使用

- 用户只发了 1 个或多个 URL，希望你直接“把内容抓出来”
- 用户要后续做整理、摘要、入库、RAG

## 默认路由（先中转，后补抓）

1. 识别输入链接（支持多个）。
2. 对每个 URL 先试可读中转双路：
   - `https://defuddle.md/<URL>`
   - `https://r.jina.ai/http://...`
3. 若中转已拿到足够正文，直接返回，不必进 Scrapling。
4. 若两路都失败、内容明显缺失、或页面结构被中转吃掉，再用 Scrapling 补抓。
5. 若是 X/Twitter 链接，也先走这套双路；只有双路失败、内容缺失、或需要更高置信复核时，才降级到 X 专用路线，官方 X API 只作备用/复核。

## Scrapling 执行命令

```powershell
D:\Software\scrapling-bot\.venv\Scripts\python.exe \
  E:\_BIGFA Free\_code\skills\scrapling-link-extractor\run_scrapling_extract.py \
  "<URL1>" "<URL2>" --out-dir "D:\Software\scrapling-bot\output"
```

执行后返回结果文件路径 + 简短内容概览。

## 可选参数

- `--insecure`：当目标站 SSL 证书链异常时启用（会降低校验安全性）。
- `--timeout <秒>`：单链接请求超时。

## 输出约定

每个 URL 产出两份文件：
- `<slug>.md`
- `<slug>.json`

并生成汇总文件：
- `summary.json`

## 注意事项

- 仅抓公开可访问内容；登录墙/验证码墙不保证成功。
- 需要登录账号的网站，也先试 `defuddle.md` / `r.jina.ai`，不要一上来就走站点专用技能。
- 抓取失败要明确报错原因（超时、403、证书问题等）并给下一步选项。
- 不要声称“100% 成功抓取”，必须以实际输出文件为准。
