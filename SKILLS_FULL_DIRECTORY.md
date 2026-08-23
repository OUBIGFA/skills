# `E:\_BIGFAFree\_code\skills` 技能全量清单与精简指南

> **统计概览**：共扫描 **236** 个技能目录。包含 12 大功能分类，已标注 Windows 兼容性、空目录、重复工具及精简建议。

## 一、分类概览与精简建议分布

| 分类编号与名称 | 技能数量 | 主要用途 | 精简/保留建议 |
| :--- | :--- | :--- | :--- |
| 1. 无效/空目录（建议清理） | **10** | 空目录或缺少 SKILL.md，无法生效 | 🔴 **强烈建议删除** |
| 10. 网络搜索、抓取与资讯监控 | **18** | 多引擎搜索、社交平台采集、GitHub趋势、宏观监控 | 🟢 **按需保留常用项** |
| 11. 学术科研、论文分析与知识库 | **22** | ArXiv论文、文献引用、统计分析、NotebookLM、Obsidian | 🟡 **建议大幅精简** |
| 12. 商业分析、内容创作与个人管理 | **18** | 商业计划验证、习惯/目标打卡、自媒体内容矩阵 | 🟢 **按需保留常用项** |
| 13. 其他通用技能 | **18** | 其他未归类工具 | 🟢 **按需保留常用项** |
| 2. macOS 专属工具（Windows环境不可用） | **5** | 依赖 Mac 系统特有 API / 应用 | 🔴 **强烈建议删除** |
| 3. 腾讯/微信生态与云服务 | **19** | 微信小程序、腾讯云、TAPD、乐享、IMA知识库等 | 🟢 **按需保留常用项** |
| 4. 前端开发、UI/UX与界面设计 | **41** | 前端框架、微调/审查/美化规则、设计系统 | 🟢 **按需保留常用项** |
| 5. 后端架构、系统运维与安全 | **19** | Node/Nest/Python/TS规范、Docker、PowerShell、安全扫描 | 🟢 **按需保留常用项** |
| 6. 研发流程规范与智能体协作 | **34** | TDD、Plan规范、代码审查、多Agent协作流程 | 🟢 **按需保留常用项** |
| 7. 办公文档、排版与文件处理 | **14** | Word/PDF/PPT/Excel 生成、编辑与提取 | 🟢 **按需保留常用项** |
| 8. AI 多媒体（图像/音视频/语音） | **12** | 生图、生视频、Whisper转录、视频剪辑、GIF制作 | 🟢 **按需保留常用项** |
| 9. 邮件收发与即时通讯 | **6** | IMAP/SMTP邮件管理、QQ邮箱、WhatsApp、WorkBuddy | 🟡 **建议大幅精简** |

---

## 二、全量技能详细清单表单

### 1. 无效/空目录（建议清理）（共 10 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `_shared` | **_shared** | （包含 6 个文件，但无 SKILL.md） | ⚠️ 缺少 SKILL.md 定义文件，无法被系统识别为有效技能，建议补全或删除。 |
| 2 | `article-writer` | **article-writer** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 3 | `bilingual_output` | **bilingual_output** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 4 | `content-planner` | **content-planner** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 5 | `daily-trending` | **daily-trending** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 6 | `evidence-based-research` | **evidence-based-research** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 7 | `stock-analyzer` | **stock-analyzer** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 8 | `stock-announcements` | **stock-announcements** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 9 | `stock-explorer` | **stock-explorer** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |
| 10 | `tencent-docs` | **tencent-docs** | （空目录，无任何文件） | ❌ 空文件夹，无任何代码或文档，建议直接删除。 |


### 10. 网络搜索、抓取与资讯监控（共 18 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `agent-reach` | **agent-reach** | Give your AI agent eyes to see the entire internet. 17 platforms via CLI, MCP, curl, and Python scripts. Zero config for 8 channels. 【路由方式】SKILL.md 包含路由表和常用命令，复杂场景需按需阅读对应分类的 ref... | 按需保留（搜索与社媒舆情监控） |
| 2 | `blogwatcher` | **blogwatcher** | Monitor blogs and RSS/Atom feeds for updates using the blogwatcher CLI. | 按需保留（搜索与社媒舆情监控） |
| 3 | `browser-use` | **browser-use** | AI-powered browser automation via browser-use CLI (`uvx browser-use`). Navigate websites, click elements, fill forms, take screenshots, extract data, and automate web tasks. Use... | 按需保留（搜索与社媒舆情监控） |
| 4 | `chrome` | **chrome** | Use when the user mentions @chrome, the Chrome plugin, Catsxp, their own browser extension, existing browser tabs, logged-in browser sessions, or browser tasks that need the use... | 按需保留（搜索与社媒舆情监控） |
| 5 | `clawfeed` | **clawfeed** | AI-powered news digest tool. Automatically generates structured summaries (4H/daily/weekly/monthly) from Twitter and RSS feeds. ClawFeed runs in **read-only mode** with zero cre... | 按需保留（搜索与社媒舆情监控） |
| 6 | `geo-fundamentals` | **geo-fundamentals** | Generative Engine Optimization for AI search engines (ChatGPT, Claude, Perplexity). | 按需保留（搜索与社媒舆情监控） |
| 7 | `github` | **github** | Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries. | 按需保留（搜索与社媒舆情监控） |
| 8 | `github-ai-trends` | **github-ai-trends** | Generate GitHub AI trending project reports as formatted text leaderboards. Fetches top-starred AI/ML/LLM repos by daily, weekly, or monthly period and renders a styled leaderbo... | 按需保留（搜索与社媒舆情监控） |
| 9 | `github-trending-cn` | **github-trending-cn** | GitHub Trending Monitor. Fetch GitHub trending repos by daily/weekly/monthly period using real GitHub Search API. Runs scripts/github_trending.py (no pip deps, stdlib only). Use... | 按需保留（搜索与社媒舆情监控） |
| 10 | `macro-monitor` | **macro-monitor** | 每日宏观数据监控和推送。自动浏览免费数据源（Trading Economics、FRED、国家统计局、央行官网、财联社等），整理整合过去24小时发布的宏观数据和政策信息，并推送给用户。通过 cron 每天晚上10点自动触发。 | 按需保留（搜索与社媒舆情监控） |
| 11 | `multi-search-engine` | **multi-search-engine** | Multi search engine integration with 17 engines (8 CN + 9 Global). Supports advanced search operators, time filters, site search, privacy engines, and WolframAlpha knowledge que... | 按需保留（搜索与社媒舆情监控） |
| 12 | `news-summary` | **news-summary** | This skill should be used when the user asks for news updates, daily briefings, or what's happening in the world. Fetches news from trusted international RSS feeds and can creat... | 按需保留（搜索与社媒舆情监控） |
| 13 | `scrapling-link-extractor` | **scrapling-link-extractor** | Use this skill whenever the user sends one or more web links and wants the page content extracted, saved, cleaned up, summarized, archived, converted to Markdown/JSON, or prepar... | 按需保留（搜索与社媒舆情监控） |
| 14 | `seo-fundamentals` | **seo-fundamentals** | SEO fundamentals, E-E-A-T, Core Web Vitals, and Google algorithm principles. | 按需保留（搜索与社媒舆情监控） |
| 15 | `weather` | **weather** | Get current weather and forecasts (no API key required). | 按需保留（搜索与社媒舆情监控） |
| 16 | `web-search` | **web-search** | Real-time web search using Playwright-controlled browser. Use this skill when you need current information, latest documentation, recent news, or any data beyond your knowledge ... | 按需保留（搜索与社媒舆情监控） |
| 17 | `xiaohongshu` | **xiaohongshu** | 小红书（RedNote）内容工具。使用场景：搜索小红书笔记并获取详情、获取首页推荐列表、获取帖子详情（正文、图片、互动数据、评论）、发表评论/回复评论、获取用户主页和笔记列表、点赞、收藏帖子、发布图文或视频笔记、热点话题跟踪与分析报告、帖子导出为长图。 | 按需保留（搜索与社媒舆情监控） |
| 18 | `xurl` | **xurl** | A Twitter research and content intelligence skill. Use to analyze Twitter profiles, threads, and conversations for identifying pain points, extracting content angles, and conver... | 按需保留（搜索与社媒舆情监控） |


### 11. 学术科研、论文分析与知识库（共 22 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `article-deep-analysis` | **article-deep-analysis** | Use when the user asks to deeply analyze an article, essay, post, speech, report, or long-form content; requests a professional content analyst; asks for analysis by layers such... | 如不做论文写作可大批精简 |
| 2 | `arxiv-reader` | **arxiv-reader** | 利用python，指定某个arxiv_id/url， 基于 LLM Agent 对这篇arxiv论文进行分类与深度阅读，直接print打印阅读笔记 | 如不做论文写作可大批精简 |
| 3 | `arxiv-watcher` | **arxiv-watcher** | Search and summarize papers from ArXiv. Use when the user asks for the latest research, specific topics on ArXiv, or a daily summary of AI papers. | 如不做论文写作可大批精简 |
| 4 | `citation-management` | **citation-management** | Comprehensive citation management for academic research. Search Google Scholar and PubMed for papers, extract accurate metadata, validate citations, and generate properly format... | 如不做论文写作可大批精简 |
| 5 | `citation-manager` | **citation-manager** | Add real references and standardize citations for research papers and theses. Supports CrossRef integration, multiple citation formats (APA/MLA/Chicago/GB-T), batch import, and ... | 如不做论文写作可大批精简 |
| 6 | `exploratory-data-analysis` | **exploratory-data-analysis** | Perform comprehensive exploratory data analysis on scientific data files across 200+ file formats. This skill should be used when analyzing any scientific data file to understan... | 如不做论文写作可大批精简 |
| 7 | `humanizer` | **humanizer** | Remove signs of AI-generated writing from text. Use when editing or reviewing text to make it sound more natural and human-written. Detects and fixes patterns including: inflate... | 如不做论文写作可大批精简 |
| 8 | `hypothesis-generation` | **hypothesis-generation** | Structured hypothesis formulation from observations. Use when you have experimental observations or data and need to formulate testable hypotheses with predictions, propose mech... | 如不做论文写作可大批精简 |
| 9 | `note-organizer` | **note-organizer** | Joplin — Note Manager — personal knowledge base. Personal productivity tool. Use when you need Joplin capabilities for personal organization, tracking, or management. | 如不做论文写作可大批精简 |
| 10 | `notebooklm-skill` | **notebooklm** | Use this skill to query your Google NotebookLM notebooks directly from Claude Code for source-grounded, citation-backed answers from Gemini. Browser automation, library manageme... | 如不做论文写作可大批精简 |
| 11 | `obsidian` | **obsidian** | Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli. | 如不做论文写作可大批精简 |
| 12 | `paper-lookup` | **paper-lookup** | Search 10 academic literature APIs for papers, preprints, citations, and open-access full text, and return results with reproducible provenance. Covers PubMed, PMC (full text), ... | 如不做论文写作可大批精简 |
| 13 | `peer-review` | **peer-review** | Structured manuscript/grant review with checklist-based evaluation. Use when writing formal peer reviews with specific criteria methodology assessment, statistical validity, rep... | 如不做论文写作可大批精简 |
| 14 | `qmd` | **qmd** | Local hybrid search for markdown notes and docs. Use when searching notes, finding related content, or retrieving documents from indexed collections. | 如不做论文写作可大批精简 |
| 15 | `scholar-evaluation` | **scholar-evaluation** | Systematically evaluate scholarly work using the ScholarEval framework, providing structured assessment across research quality dimensions including problem formulation, methodo... | 如不做论文写作可大批精简 |
| 16 | `scientific-brainstorming` | **scientific-brainstorming** | Creative research ideation and exploration. Use for open-ended brainstorming sessions, exploring interdisciplinary connections, challenging assumptions, or identifying research ... | 如不做论文写作可大批精简 |
| 17 | `scientific-critical-thinking` | **scientific-critical-thinking** | Evaluate scientific claims and evidence quality. Use for assessing experimental design validity, identifying biases and confounders, applying evidence grading frameworks (GRADE,... | 如不做论文写作可大批精简 |
| 18 | `scientific-schematics` | **scientific-schematics** | Create publication-quality scientific diagrams using Nano Banana 2 AI with smart iterative refinement. Uses Gemini 3.1 Pro Preview for quality review. Only regenerates if qualit... | 如不做论文写作可大批精简 |
| 19 | `scientific-visualization` | **scientific-visualization** | Meta-skill for publication-ready figures. Use when creating journal submission figures requiring multi-panel layouts, significance annotations, error bars, colorblind-safe palet... | 如不做论文写作可大批精简 |
| 20 | `statistical-analysis` | **statistical-analysis** | Guided statistical analysis for research data - test selection, assumption checking, effect sizes, power analysis, Bayesian alternatives, and APA-formatted reporting. Use whenev... | 如不做论文写作可大批精简 |
| 21 | `statistical-power` | **statistical-power** | Sample-size and statistical power calculations for planning studies. Use whenever someone asks "how many subjects/samples/replicates do I need", wants an a priori power analysis... | 如不做论文写作可大批精简 |
| 22 | `summarize` | **summarize** | Summarize or extract text/transcripts from URLs, podcasts, and local files (great fallback for “transcribe this YouTube/video”). | 如不做论文写作可大批精简 |


### 12. 商业分析、内容创作与个人管理（共 18 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `agent-mbti` | **agent-mbti** | AI Agent personality diagnosis and configuration system based on MBTI framework. Use when users want to (1) test/diagnose an Agent's personality type, (2) understand the gap bet... | 按需保留 |
| 2 | `content-factory` | **content-factory** | Multi-agent content production system. One piece of source content becomes many formats — social posts, email, scripts, headlines, and more. Five specialized agent personas: Wri... | 按需保留 |
| 3 | `content-repurposer` | **content-repurposer** | Transform long-form content into platform-optimized snippets. Your agent takes one blog post, video transcript, or podcast notes and generates ready-to-publish Twitter threads, ... | 按需保留 |
| 4 | `cron` | **cron** | Schedule reminders and recurring tasks. | 按需保留 |
| 5 | `earnings-tracker` | **earnings-tracker** | AI 驱动的财报追踪器，自动扫描 A 股/美股财报日历，推送重要财报更新 | 按需保留 |
| 6 | `films-search` | **films-search** | Search cloud drives for downloadable film and TV resources (movies, TV series, anime). Use this skill when the user wants to download a specific movie or TV show. Do NOT use for... | 按需保留 |
| 7 | `find-skills` | **find-skills** | Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extendin... | 按需保留 |
| 8 | `goal-tracker` | **goal-tracker** | Track long-term goals with milestones, daily logging, and accountability. Use when users want to set goals, log daily progress, update milestones, generate weekly summaries, or ... | 按需保留 |
| 9 | `habit-tracker` | **habit-tracker** | Build habits with streaks, reminders, and progress visualization. Use when users want to create daily/weekly habits, track streaks, set reminders, or view habit progress over time. | 按需保留 |
| 10 | `healthcheck` | **healthcheck** | Track water and sleep with JSON file storage. | 按需保留 |
| 11 | `idea-validator` | **idea-validator** | Validate startup ideas using Hexa's Opportunity Memo framework and Perceived Created Value (PCV) methodology. Assess problem-solution fit, market opportunity, and determine if a... | 按需保留 |
| 12 | `local-tools` | **local-tools** | Access local system resources including Calendar on macOS and Windows. Use this skill when you need to manage user's schedule directly on their device. | 按需保留 |
| 13 | `market-researcher` | **market-researcher** | Market research specialist focused on comprehensive market analysis, consumer behavior insights, and market opportunity identification. Excels at quantitative market sizing (TAM... | 按需保留 |
| 14 | `music-search` | **music-search** | Search cloud drives for downloadable music resources (songs, albums, lossless audio). Use this skill when the user wants to download a specific song or album. Do NOT use for gen... | 按需保留 |
| 15 | `startup-pressure-test` | **startup-pressure-test** | Brutally evaluate and refine startup ideas with practical early-stage startup frameworks. Use when Codex is asked to pressure-test a startup idea, validate whether the problem i... | 按需保留 |
| 16 | `teach-impeccable` | **teach-impeccable** | One-time setup that gathers design context for your project and saves it to your AI config file. Run once to establish persistent design guidelines. | 按需保留 |
| 17 | `technology-news-search` | **technology-search** | Search tech blogs, developer forums, and IT media (TechCrunch, Hacker News, 36氪, etc.) for software and hardware industry updates with heat ranking and EN↔CN translation. Use th... | 按需保留 |
| 18 | `trello` | **trello** | Manage Trello boards, lists, and cards via the Trello REST API. | 按需保留 |


### 13. 其他通用技能（共 18 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `andonq` | **andonq** | 腾讯云 AndonQ 工单与智能客服助手 — 不切窗口、不排队，即刻获得腾讯云全产品线专业解答。支持工单查询（列表/详情/流水）、创建工单（自动匹配产品分类）、集团工单与需求单管理、腾讯云全产品线智能问答，以及通过 tccli 调用腾讯云任意云 API（如 CVM、CBS、CAM 等）。当用户查询工单、查看工单详情、创建工单、咨询腾讯云产品问题（如 C... | 按需评估 |
| 2 | `audit` | **audit** | Perform comprehensive audit of interface quality across accessibility, performance, theming, and responsive design. Generates detailed report of issues with severity ratings and... | 按需评估 |
| 3 | `brainstorming` | **brainstorming** | You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design b... | 按需评估 |
| 4 | `brooks-audit` | **brooks-audit** | Architecture audit that maps module dependencies, checks layering integrity, and flags structural decay across a codebase, drawing on twelve classic engineering books. Triggers ... | 按需评估 |
| 5 | `brooks-debt` | **brooks-debt** | Tech debt assessment that identifies, classifies, and prioritizes maintainability problems — helping teams build a refactoring roadmap — drawing on twelve classic engineering bo... | 按需评估 |
| 6 | `brooks-health` | **brooks-health** | Combined codebase health dashboard that scores a project across all four quality dimensions — PR quality, architecture, tech debt, and test quality — in a single pass, drawing o... | 按需评估 |
| 7 | `brooks-review` | **brooks-review** | PR code review that surfaces decay risks, design smells, and maintainability issues with concrete Symptom → Source → Consequence → Remedy findings, drawing on twelve classic eng... | 按需评估 |
| 8 | `brooks-sweep` | **brooks-sweep** | Full-sweep mode: runs a unified analysis across all quality dimensions — code decay, architecture, tech debt, and test quality — then applies fixes directly to the codebase. Saf... | 按需评估 |
| 9 | `brooks-test` | **brooks-test** | Test quality review drawing on twelve classic engineering books — with primary focus on xUnit Test Patterns, The Art of Unit Testing, How Google Tests Software, and Working Effe... | 按需评估 |
| 10 | `extract` | **extract** | Extract and consolidate reusable components, design tokens, and patterns into your design system. Identifies opportunities for systematic reuse and enriches your component library. | 按需评估 |
| 11 | `fullstack-dev` | **fullstack-dev** | Full-stack backend architecture and frontend-backend integration guide. TRIGGER when: building a full-stack app, creating REST API with frontend, scaffolding backend service, bu... | 按需评估 |
| 12 | `gog` | **gog** | Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs. | 按需评估 |
| 13 | `i18n-localization` | **i18n-localization** | Internationalization and localization patterns. Detecting hardcoded strings, managing translations, locale files, RTL support. | 按需评估 |
| 14 | `install-download-guard` | **install-download-guard** | Guardrail for any install/download/setup/change request, AND resource download organizer. Use whenever the user asks to install software, dependencies, skills, plugins, scripts,... | 按需评估 |
| 15 | `local-install-deploy-guard` | **local-install-deploy-guard** | Create and review formal local installation and deployment plans for this Windows workstation. Use when the user asks to install software, deploy local services, download resour... | 按需评估 |
| 16 | `proxy-geo-rename` | **proxy-geo-rename** | 对代理配置文件（sing-box JSON）中的节点做真实出口地理检测，并按【地区/国家emoji 地区/国家_具体位置_编号】格式统一重命名（如 🇯🇵 日本_东京_8），还能合并多个订阅去重、按地区排序、生成可导入客户端的干净配置。检测通过本机已有 sing-box 内核真实连接每个节点，8 个独立地理库投票 + Cloudflare 接入机房物理决... | 按需评估 |
| 17 | `taste-skill` | **full-output-enforcement** | Overrides default LLM truncation behavior. Enforces complete code generation, bans placeholder patterns, and handles token-limit splits cleanly. Apply to any task requiring exha... | 按需评估 |
| 18 | `webapp-testing` | **webapp-testing** | Web application testing principles. E2E, Playwright, deep audit strategies. | 按需评估 |


### 2. macOS 专属工具（Windows环境不可用）（共 5 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `apple-notes` | **apple-notes** | Manage Apple Notes via the `memo` CLI on macOS (create, view, edit, delete, search, move, and export notes). Use when a user asks to add a note, list notes, search notes, or man... | 🍎 依赖 macOS 系统专属应用与底层接口（如 Apple 备忘录、提醒事项、iMessage、Things3、Peekaboo），Windows 环境下无法运行，建议删除/禁用。 |
| 2 | `apple-reminders` | **apple-reminders** | Manage Apple Reminders via the `remindctl` CLI on macOS (list, add, edit, complete, delete). Supports lists, date filters, and JSON/plain output. | 🍎 依赖 macOS 系统专属应用与底层接口（如 Apple 备忘录、提醒事项、iMessage、Things3、Peekaboo），Windows 环境下无法运行，建议删除/禁用。 |
| 3 | `imsg` | **imsg** | iMessage/SMS CLI for listing chats, history, watch, and sending. | 🍎 依赖 macOS 系统专属应用与底层接口（如 Apple 备忘录、提醒事项、iMessage、Things3、Peekaboo），Windows 环境下无法运行，建议删除/禁用。 |
| 4 | `peekaboo` | **peekaboo** | Capture and automate macOS UI with the Peekaboo CLI. | 🍎 依赖 macOS 系统专属应用与底层接口（如 Apple 备忘录、提醒事项、iMessage、Things3、Peekaboo），Windows 环境下无法运行，建议删除/禁用。 |
| 5 | `things-mac` | **things-mac** | Manage Things 3 via the `things` CLI on macOS (add/update projects+todos via URL scheme; read/search/list from the local Things database). Use when a user asks to add a task to ... | 🍎 依赖 macOS 系统专属应用与底层接口（如 Apple 备忘录、提醒事项、iMessage、Things3、Peekaboo），Windows 环境下无法运行，建议删除/禁用。 |


### 3. 腾讯/微信生态与云服务（共 19 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `cloudbase` | **cloudbase** | CloudBase is a full-stack development and deployment toolkit for building and launching websites, Web apps, 微信小程序 (WeChat Mini Programs), and mobile apps with backend, database,... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 2 | `cloudq` | **cloudq** | 用户咨询腾讯云产品资源、AWS、阿里云等多云资源时，查看智能顾问架构图、架构目录、架构详情、架构评估结果、绘制架构图、开通智能顾问时、AI智能巡检、AI容量监测、AI混沌演练、AI云诊断、主动预警、架构健康度、云运维问答、云资源查询、云成本优化、安全合规、云资源盘点、闲置资源检查、云产品最佳实践等AIOps、ChatOps、CloudOps操作时使用。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 3 | `cnb-skill` | **cnb-skill** | Interact with CNB (Cloud Native Build) platform via OpenAPI. Manage organizations, repositories, issues, PRs, merge requests, pipelines, releases, artifacts, workspaces, members... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 4 | `cos-vectors` | **cos-vectors** | Manage Tencent Cloud COS vector buckets via cos-python-sdk-v5 CosVectorsClient. Full lifecycle: create/delete/list vector buckets, manage bucket policies, create/query/list/dele... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 5 | `ima-skills` | **ima-skills** | 统一的 IMA OpenAPI 技能，支持笔记管理和知识库操作。 当用户提到知识库、资料库、笔记、备忘录、记事，或者想要上传文件、添加网页到知识库、 搜索知识库内容、搜索/浏览/创建/编辑笔记时，使用此 skill。 即使用户没有明确说"知识库"或"笔记"，只要意图涉及文件上传到知识库、网页收藏、 知识搜索、个人文档存取（如"帮我记一下"、"搜一下知识... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 6 | `lexiang-knowledge-base` | **lexiang-knowledge-base** | 用于访问乐享知识库平台的专用 skill。当用户明确提到「乐享」「lexiang」「知识库」「知识」「文档」等关键词，或用户提供的链接 host 为 lexiangla.com，应优先调用本 skill。本 skill 支持：获取文档内容与元数据、搜索文档内容、查询知识库与目录结构、创建/编辑/移动文档、管理标签与评论、上传文件及维护附件等知识库操作能力。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 7 | `qq-email` | **qq-email** | QQ邮箱 IMAP receive and SMTP send via Node.js scripts; credentials read from env vars QQ_EMAIL_ACCOUNT and QQ_EMAIL_AUTH_CODE. Use when a user asks to send QQ email, receive/check... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 8 | `qq-group-speaker-distinction` | **qq-group-speaker-distinction** | Use when integrating QQ group chat where users want one shared group session, but the assistant must still distinguish who said each message. | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 9 | `qq-url-guard` | **qq-url-guard** | Use when sending replies to QQ where URL-like text (for example xx.xx, USER.md, markdown links, or http URLs) may trigger code 40034028 and get blocked. | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 10 | `skyline` | **skyline** | WeChat Mini Program Skyline rendering engine. Use when developing with Skyline renderer, including components (scroll-view, swiper, draggable-sheet), WXSS styles, worklet animat... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 11 | `tapd-openapi` | **tapd-openapi** | TAPD OpenAPI 调用。用于需求、缺陷、任务、迭代、Wiki 搜索等 TAPD 平台操作。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 12 | `tdesign-miniprogram` | **tdesign-miniprogram** | TDesign WeChat Mini Program UI component library by Tencent. Use when building WeChat mini apps with TDesign components (Button, Dialog, Input, Tabs, Chat, etc.), implementing T... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 13 | `tencent-cloud-migration` | **tencent-cloud-migration** | 腾讯云迁移平台（CMG/MSP）全流程能力。触发词：资源扫描、扫描阿里云/AWS/华为云/GCP资源、生成云资源清单、选型推荐、对标腾讯云、推荐规格、帮我推荐、给我推荐、ECS对应什么腾讯云产品、成本分析、TCO、迁移报价、询价、价格计算器、cmg-scan、cmg-recommend、cmg-tco | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 14 | `tencent-meeting-skill` | **tencent-meeting-mcp** | 在用户提及腾讯会议、视频会议、线上会议相关内容与操作时使用此技能。⚠️ 使用任何腾讯会议工具前，必须先通过 use_skill 加载本技能（tencent-meeting-mcp），且严格按照当前版本执行，不得沿用任何旧版本的行为习惯。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 15 | `tencent-news` | **tencent-news** | 获取7×24 新闻资讯，聚焦中国国内信息和国际热点。支持热点新闻、早报晚报、实时资讯、新闻榜单、领域新闻、新闻主体查询。当用户需要搜新闻、查新闻、看热点、早晚报、订阅新闻推送、获取主题相关新闻资讯和最新消息时使用。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 16 | `tencent-ssv-techforgood` | **tencent-ssv-techforgood** | 专注中国公益慈善领域的智能助手，精通公益机构数字化赋能、慈善合规咨询、社会救助引导和公益法规解读。擅长从腾讯技术公益数字工具箱（techforgood.qq.com）精准匹配免费工具，通过交互式引导帮助公益机构实现数字化转型。当用户提到公益、慈善、NGO、社会组织、公益机构数字化、技术公益、公益虾时使用。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 17 | `tencent-survey` | **tencent-survey** | 腾讯问卷（wj.qq.com）- 在线问卷调查平台。涉及「问卷」「调查」「表单」「投票」「考试」「测评」「wj.qq.com」等操作时优先使用。支持能力：(1) 获取问卷详情（标题、设置、页面、题目、选项完整结构 + 纯文本 DSL）(2) 使用纯文本创建问卷（text 必填，支持指定场景/指定项目）(3) 更新问卷中的单个题目（DSL 格式）(4) ... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 18 | `tencentcloud-cos` | **tencentcloud-cos** | 腾讯云对象存储(COS)和数据万象(CI)集成技能。当用户需要上传、下载、管理云存储文件，或需要进行图片处理（质量评估、超分辨率、抠图、二维码识别、水印）、智能图片搜索、文档转PDF、视频智能封面生成等操作时使用此技能。 | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |
| 19 | `wechat-miniprogram` | **wechat-miniprogram** | WeChat Mini Program (微信小程序) development framework. Use when building WeChat mini apps with WXML templates, WXSS styles, WXS scripting, component development, WeChat API integrat... | 保留（如开发微信小程序、使用腾讯云/TAPD/乐享/IMA则必须） |


### 4. 前端开发、UI/UX与界面设计（共 41 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `adapt` | **adapt** | Adapt designs to work across different screen sizes, devices, contexts, or platforms. Ensures consistent experience across varied environments. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 2 | `android-native-dev` | **android-native-dev** | Android native application development and UI design guide. Covers Material Design 3, Kotlin/Compose development, project configuration, accessibility, and build troubleshooting... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 3 | `app-builder` | **app-builder** | Main application building orchestrator. Creates full-stack applications from natural language requests. Determines project type, selects tech stack, coordinates agents. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 4 | `brand-guidelines` | **brand-guidelines** | Applies Anthropic's official brand colors and typography to any sort of artifact that may benefit from having Anthropic's look-and-feel. Use it when brand colors or style guidel... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 5 | `brandkit` | **brandkit** | Premium brand-kit image generation skill for creating high-end brand-guidelines boards, logo systems, identity decks, and visual-world presentations. Trained for minimalist, cin... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 6 | `canvas-design` | **canvas-design** | Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other s... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 7 | `clarify` | **clarify** | Improve unclear UX copy, error messages, microcopy, labels, and instructions. Makes interfaces easier to understand and use. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 8 | `critique` | **critique** | Evaluate design effectiveness from a UX perspective. Assesses visual hierarchy, information architecture, emotional resonance, and overall design quality with actionable feedback. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 9 | `database-design` | **database-design** | Database design principles and decision-making. Schema design, indexing strategy, ORM selection, serverless databases. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 10 | `design-taste-frontend` | **design-taste-frontend** | Senior UI/UX Engineer. Architect digital interfaces overriding default LLM biases. Enforces metric-based rules, strict component architecture, CSS hardware acceleration, and bal... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 11 | `distill` | **distill** | Strip designs to their essence by removing unnecessary complexity. Great design is simple, powerful, and clean. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 12 | `experimental-design` | **experimental-design** | Design experiments and studies BEFORE data is collected — choosing a design, randomizing, blocking, and laying out treatment combinations so the results will actually be interpr... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 13 | `flutter-dev` | **flutter-dev** | Flutter cross-platform development guide covering widget patterns, Riverpod/Bloc state management, GoRouter navigation, performance optimization, and platform-specific implement... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 14 | `frontend-dev` | **frontend-dev** | Full-stack frontend development combining premium UI design, cinematic animations, AI-generated media assets, persuasive copywriting, and visual art. Builds complete, visually s... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 15 | `guizang-ppt-skill` | **guizang-ppt-skill** | 生成横向翻页网页 PPT（单 HTML 文件），含 WebGL 背景、章节幕封、数据大字报、图片网格等模板。提供两种风格：① "电子杂志 × 电子墨水"（衬线 + 流体背景 + 暖色） ② "瑞士国际主义"（无衬线 + 网格点阵 + IKB/柠檬黄/柠檬绿/安全橙高亮）。当用户需要制作分享 / 演讲 / 发布会风格的网页 PPT，或提到"杂志风 PPT... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 16 | `harden` | **harden** | Improve interface resilience through better error handling, i18n support, text overflow handling, and edge case management. Makes interfaces robust and production-ready. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 17 | `huashu-design` | **huashu-design** | 花叔Design（Huashu-Design）——用HTML做高保真原型、交互Demo、幻灯片、动画、设计变体探索+设计方向顾问+专家评审的一体化设计能力。HTML是工具不是媒介，根据任务embody不同专家（UX设计师/动画师/幻灯片设计师/原型师），避免web design tropes。触发词：做原型、设计Demo、交互原型、HTML演示、动画D... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 18 | `image-to-code` | **image-to-code** | Elite website image-to-code skill for Codex. For visually important web tasks, it must first generate the design image(s) itself, deeply analyze them, then implement the website... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 19 | `imagegen-frontend-mobile` | **imagegen-frontend-mobile** | Elite mobile app image-generation skill for creating premium, app-native screen concepts and flows. Designed for iOS, Android, and cross-platform mobile products. Prioritizes cl... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 20 | `imagegen-frontend-web` | **imagegen-frontend-web** | Elite frontend image-direction skill for generating premium, conversion-aware website design references. CRITICAL OUTPUT RULE — generate ONE separate horizontal image FOR EVERY ... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 21 | `ios-application-dev` | **ios-application-dev** | iOS application development guide covering UIKit, SnapKit, and SwiftUI. Includes touch targets, safe areas, navigation patterns, Dynamic Type, Dark Mode, accessibility, collecti... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 22 | `mcp-builder` | **mcp-builder** | MCP (Model Context Protocol) server building principles. Tool design, resource patterns, best practices. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 23 | `minimalist-ui` | **minimalist-ui** | Clean editorial-style interfaces. Warm monochrome palette, typographic contrast, flat bento grids, muted pastels. No gradients, no heavy shadows. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 24 | `mobile-design` | **mobile-design** | Mobile-first design thinking and decision-making for iOS and Android apps. Touch interaction, performance patterns, platform conventions. Teaches principles, not fixed values. U... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 25 | `nextjs-best-practices` | **nextjs-best-practices** | Next.js App Router principles. Server Components, data fetching, routing patterns. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 26 | `normalize` | **normalize** | Normalize design to match your design system and ensure consistency | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 27 | `onboard` | **onboard** | Design or improve onboarding flows, empty states, and first-time user experiences. Helps users get started successfully and understand value quickly. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 28 | `optimize` | **optimize** | Improve interface performance across loading speed, rendering, animations, images, and bundle size. Makes experiences faster and smoother. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 29 | `polish` | **polish** | Final quality pass before shipping. Fixes alignment, spacing, consistency, and detail issues that separate good from great. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 30 | `qiaomu-design-advisor` | **qiaomu-design-advisor** | 偏执型设计顾问 — Jobs 式产品直觉 + Rams 式功能纯粹主义。重新设计页面、审视 UI 方案、优化交互体验时使用。 触发词："重新设计"、"redesign"、"优化界面"、"优化交互"、"设计方案"、"UI 审查"、"这个页面不行"、"界面不好看"、"帮我看看设计"、"设计建议"、"/design-advisor"。 适用于：(1) 页面/... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 31 | `quieter` | **quieter** | Tone down overly bold or visually aggressive designs. Reduces intensity while maintaining design quality and impact. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 32 | `react-native-dev` | **react-native-dev** | React Native and Expo development guide covering components, styling, animations, navigation, state management, forms, networking, performance optimization, testing, native capa... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 33 | `react-patterns` | **react-patterns** | Modern React patterns and principles. Hooks, composition, performance, TypeScript best practices. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 34 | `redesign-existing-projects` | **redesign-existing-projects** | Upgrades existing websites and apps to premium quality. Audits current design, identifies generic AI patterns, and applies high-end design standards without breaking functionali... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 35 | `remotion` | **remotion-best-practices** | Best practices for Remotion - Video creation in React | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 36 | `shader-dev` | **shader-dev** | Comprehensive GLSL shader techniques for creating stunning visual effects — ray marching, SDF modeling, fluid simulation, particle systems, procedural generation, lighting, post... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 37 | `tailwind-patterns` | **tailwind-patterns** | Tailwind CSS v4 principles. CSS-first configuration, container queries, modern patterns, design token architecture. | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 38 | `transitions-dev` | **transitions-dev** | Production-ready CSS transitions for web apps. Use when implementing notification badges, dropdowns, modals, panel reveals, page transitions, card resizes, number pop-ins, text ... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 39 | `uncodixfy` | **uncodixfy** | Prevents generic AI/Codex UI patterns when generating frontend code. Use this skill whenever generating HTML, CSS, React, Vue, Svelte, or any frontend UI code to enforce clean, ... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 40 | `visual-design` | **visual-design** | Visual design rules for clean, readable, low-fatigue interfaces. Use when creating or reviewing any UI to enforce restraint in typography weight, element density, shadows, decor... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |
| 41 | `web-design-guidelines` | **web-design-guidelines** | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best prac... | 按需保留（UI微调类工具众多，存在一定细粒度重合） |


### 5. 后端架构、系统运维与安全（共 19 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `api-patterns` | **api-patterns** | API design principles and decision-making. REST vs GraphQL vs tRPC selection, response formats, versioning, pagination. | 建议保留（核心后端与运维开发参考规范） |
| 2 | `architecture` | **architecture** | Architectural decision-making framework. Requirements analysis, trade-off evaluation, ADR documentation. Use when making architecture decisions or analyzing system design. | 建议保留（核心后端与运维开发参考规范） |
| 3 | `bash-linux` | **bash-linux** | Bash/Linux terminal patterns. Critical commands, piping, error handling, scripting. Use when working on macOS or Linux systems. | 建议保留（核心后端与运维开发参考规范） |
| 4 | `deployment-procedures` | **deployment-procedures** | Production deployment principles and decision-making. Safe deployment workflows, rollback strategies, and verification. Teaches thinking, not scripts. | 建议保留（核心后端与运维开发参考规范） |
| 5 | `develop-web-game` | **develop-web-game** | Use when Codex is building or iterating on a web game (HTML/JS) and needs a reliable development + testing loop: implement small changes, run a Playwright-based test script with... | 建议保留（核心后端与运维开发参考规范） |
| 6 | `docker-expert` | **docker-expert** | Docker containerization expert with deep knowledge of multi-stage builds, image optimization, container security, Docker Compose orchestration, and production deployment pattern... | 建议保留（核心后端与运维开发参考规范） |
| 7 | `game-development` | **game-development** | Game development orchestrator. Routes to platform-specific skills based on project needs. | 建议保留（核心后端与运维开发参考规范） |
| 8 | `mcporter` | **mcporter** | Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation. | 建议保留（核心后端与运维开发参考规范） |
| 9 | `nestjs-expert` | **nestjs-expert** | Nest.js framework expert specializing in module architecture, dependency injection, middleware, guards, interceptors, testing with Jest/Supertest, TypeORM/Mongoose integration, ... | 建议保留（核心后端与运维开发参考规范） |
| 10 | `nodejs-best-practices` | **nodejs-best-practices** | Node.js development principles and decision-making. Framework selection, async patterns, security, and architecture. Teaches thinking, not copying. | 建议保留（核心后端与运维开发参考规范） |
| 11 | `performance-profiling` | **performance-profiling** | Performance profiling principles. Measurement, analysis, and optimization techniques. | 建议保留（核心后端与运维开发参考规范） |
| 12 | `powershell-windows` | **powershell-windows** | PowerShell Windows patterns. Critical pitfalls, operator syntax, error handling. | 建议保留（核心后端与运维开发参考规范） |
| 13 | `prisma-expert` | **prisma-expert** | Prisma ORM expert for schema design, migrations, query optimization, relations modeling, and database operations. Use PROACTIVELY for Prisma schema issues, migration problems, q... | 建议保留（核心后端与运维开发参考规范） |
| 14 | `python-patterns` | **python-patterns** | Python development principles and decision-making. Framework selection, async patterns, type hints, project structure. Teaches thinking, not copying. | 建议保留（核心后端与运维开发参考规范） |
| 15 | `red-team-tactics` | **red-team-tactics** | Red team tactics principles based on MITRE ATT&CK. Attack phases, detection evasion, reporting. | 建议保留（核心后端与运维开发参考规范） |
| 16 | `server-management` | **server-management** | Server management principles and decision-making. Process management, monitoring strategy, and scaling decisions. Teaches thinking, not commands. | 建议保留（核心后端与运维开发参考规范） |
| 17 | `tmux` | **tmux** | Remote-control tmux sessions for interactive CLIs by sending keystrokes and scraping pane output. | 建议保留（核心后端与运维开发参考规范） |
| 18 | `typescript-expert` | **typescript-expert** | - TypeScript and JavaScript expert with deep knowledge of type-level programming, performance optimization, monorepo management, migration strategies, and modern tooling. Use PR... | 建议保留（核心后端与运维开发参考规范） |
| 19 | `vulnerability-scanner` | **vulnerability-scanner** | Advanced vulnerability analysis principles. OWASP 2025, Supply Chain Security, attack surface mapping, risk prioritization. | 建议保留（核心后端与运维开发参考规范） |


### 6. 研发流程规范与智能体协作（共 34 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `behavioral-modes` | **behavioral-modes** | AI operational modes (brainstorm, implement, debug, review, teach, ship, orchestrate). Use to adapt behavior based on task type. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 2 | `clean-code` | **clean-code** | Pragmatic coding standards - concise, direct, no over-engineering, no unnecessary comments | 按需精简（部分超级工作流/测试规范存在重叠） |
| 3 | `code-review-checklist` | **code-review-checklist** | Code review guidelines covering code quality, security, and best practices. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 4 | `code-rules` | **code-rules** | Coding rules and development discipline for all code-related tasks. Use this skill whenever the user asks you to write, modify, debug, refactor, review, or test any code. Always... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 5 | `codegraph-code` | **codegraph-code** | ﻿--- name: codegraph-code | 按需精简（部分超级工作流/测试规范存在重叠） |
| 6 | `create-plan` | **create-plan** | Create a concise plan. Use when a user explicitly asks for a plan related to a coding task. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 7 | `dispatching-parallel-agents` | **dispatching-parallel-agents** | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies | 按需精简（部分超级工作流/测试规范存在重叠） |
| 8 | `executing-plans` | **executing-plans** | Use when you have a written implementation plan to execute in a separate session with review checkpoints | 按需精简（部分超级工作流/测试规范存在重叠） |
| 9 | `finishing-a-development-branch` | **finishing-a-development-branch** | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work | 按需精简（部分超级工作流/测试规范存在重叠） |
| 10 | `full-output-enforcement` | **full-output-enforcement** | Overrides default LLM truncation behavior. Enforces complete code generation, bans placeholder patterns, and handles token-limit splits cleanly. Apply to any task requiring exha... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 11 | `handoff-writer` | **handoff-writer** | Write a handoff markdown file for the next AI agent so work can continue in a new session with minimal context loss. Triggers when user mentions: - "handoff" - "交接" - "交接文件" - "... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 12 | `lint-and-validate` | **lint-and-validate** | Automatic quality control, linting, and static analysis procedures. Use after every code modification to ensure syntax correctness and project standards. Triggers onKeywords: li... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 13 | `oracle` | **oracle** | Use the @steipete/oracle CLI to bundle a prompt plus the right files and get a second-model review (API or browser) for debugging, refactors, design checks, or cross-validation. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 14 | `parallel-agents` | **parallel-agents** | Multi-agent orchestration patterns. Use when multiple independent tasks can run with different domain expertise or when comprehensive analysis requires multiple perspectives. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 15 | `plan-writing` | **plan-writing** | Structured task planning with clear breakdowns, dependencies, and verification criteria. Use when implementing features, refactoring, or any multi-step work. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 16 | `receiving-code-review` | **receiving-code-review** | Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verific... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 17 | `requesting-code-review` | **requesting-code-review** | Use when completing tasks, implementing major features, or before merging to verify work meets requirements | 按需精简（部分超级工作流/测试规范存在重叠） |
| 18 | `skill-creator` | **skill-creator** | Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, update or optimize an existing skill, r... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 19 | `skill-scanner` | **skill-scanner** | Scan any agent skill for security risks before you install or use it. Powered by Tencent Zhuque Lab A.I.G (AI-Infra-Guard). 100% local static analysis — no file contents or cred... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 20 | `skill-vetter` | **skill-vetter** | Security-first skill vetting for AI agents. Use before installing any skill from ClawdHub, GitHub, or other sources. Checks for red flags, permission scope, and suspicious patte... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 21 | `skills-security-check` | **skills-security-check** | 腾讯云鼎实验室出品，Skill安全审查工具。对用户指定的skill.md文件及其配套的文档、程序、脚本等进行全面安全审计，确保引用安全 | 按需精简（部分超级工作流/测试规范存在重叠） |
| 22 | `subagent-driven-development` | **subagent-driven-development** | Use when executing implementation plans with independent tasks in the current session | 按需精简（部分超级工作流/测试规范存在重叠） |
| 23 | `superpowers-main` | **brainstorming** | You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design b... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 24 | `systematic-debugging` | **systematic-debugging** | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes | 按需精简（部分超级工作流/测试规范存在重叠） |
| 25 | `target-scope-verification` | **target-scope-verification** | 通用查询防混淆流程。用于任何“查对象资源/配置/插件/扩展/目录”类任务，强制先锁定目标范围、再分层检查、最后基于证据下结论。 | 按需精简（部分超级工作流/测试规范存在重叠） |
| 26 | `tdd-workflow` | **tdd-workflow** | Test-Driven Development workflow principles. RED-GREEN-REFACTOR cycle. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 27 | `test-driven-development` | **test-driven-development** | Use when implementing any feature or bugfix, before writing implementation code | 按需精简（部分超级工作流/测试规范存在重叠） |
| 28 | `testing-patterns` | **testing-patterns** | Testing patterns and principles. Unit, integration, mocking strategies. | 按需精简（部分超级工作流/测试规范存在重叠） |
| 29 | `using-git-worktrees` | **using-git-worktrees** | Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or gi... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 30 | `using-superpowers` | **using-superpowers** | Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions | 按需精简（部分超级工作流/测试规范存在重叠） |
| 31 | `verification-before-completion` | **verification-before-completion** | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any s... | 按需精简（部分超级工作流/测试规范存在重叠） |
| 32 | `writing-plans` | **writing-plans** | Use when you have a spec or requirements for a multi-step task, before touching code | 按需精简（部分超级工作流/测试规范存在重叠） |
| 33 | `writing-skills` | **writing-skills** | Use when creating new skills, editing existing skills, or verifying skills work before deployment | 按需精简（部分超级工作流/测试规范存在重叠） |
| 34 | `yansu-agent-cli` | **yansu-agent-cli** | Use the bundled Yansu CLI to sync project knowledge/context/skills and run Yansu workflow commands. | 按需精简（部分超级工作流/测试规范存在重叠） |


### 7. 办公文档、排版与文件处理（共 14 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `FBS-BookWriter` | **FBS-BookWriter** | 福帮手出品\|中文人机协同著书与长文档：书籍、企业/培训手册、行业白皮书与指南；S0–S6 工作流、强制联网查证、S/P/C/B 分层审校、中文排版与 MD/HTML 交付。 触发词（精选）：写书、写长篇、写手册、写白皮书、写行业指南、协同写书、定大纲、写章节、排版构建、导出、去AI味、质量自检、图文书。 | 按需保留（Office格式处理全套，部分与minimax重复） |
| 2 | `cpa-codex-free` | **cpa-codex-free** | CPA认证文件自动生成及清理 | 按需保留（Office格式处理全套，部分与minimax重复） |
| 3 | `documentation-templates` | **documentation-templates** | Documentation templates and structure guidelines. README, API docs, code comments, and AI-friendly documentation. | 按需保留（Office格式处理全套，部分与minimax重复） |
| 4 | `docx` | **docx** | Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. When Claude needs to work with p... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 5 | `markitdown-assistant` | **markitdown-assistant** | Use MarkItDown to convert user-provided files or links into clean Markdown, then optionally produce chunked JSONL for RAG ingestion. Trigger when BIGFA sends a document/file/lin... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 6 | `minimax-docx` | **minimax-docx** | Professional DOCX document creation, editing, and formatting using OpenXML SDK (.NET). Three pipelines: (A) create new documents from scratch, (B) fill/edit content in existing ... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 7 | `minimax-pdf` | **minimax-pdf** | Use this skill when visual quality and design identity matter for a PDF. CREATE (generate from scratch): "make a PDF", "generate a report", "write a proposal", "create a resume"... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 8 | `minimax-xlsx` | **minimax-xlsx** | Open, create, read, analyze, edit, or validate Excel/spreadsheet files (.xlsx, .xlsm, .csv, .tsv). Use when the user asks to create, build, modify, analyze, read, validate, or f... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 9 | `nano-pdf` | **nano-pdf** | Edit PDFs with natural-language instructions using the nano-pdf CLI. | 按需保留（Office格式处理全套，部分与minimax重复） |
| 10 | `pdf` | **pdf** | Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF for... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 11 | `pptx` | **pptx** | Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying or editing content, (... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 12 | `pptx-generator` | **pptx-generator** | Generate, edit, and read PowerPoint presentations. Create from scratch with PptxGenJS (cover, TOC, content, section divider, summary slides), edit existing PPTX via XML workflow... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 13 | `srt-subtitle-translator` | **srt-subtitle-translator** | Hand-translate subtitle files — SRT, WebVTT (.vtt), and ASS/SSA (.ass) — into natural, professional subtitles in the requested target language, Simplified Chinese by default, wi... | 按需保留（Office格式处理全套，部分与minimax重复） |
| 14 | `xlsx` | **xlsx** | Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work with spreadsheets (.... | 按需保留（Office格式处理全套，部分与minimax重复） |


### 8. AI 多媒体（图像/音视频/语音）（共 12 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `gif-sticker-maker` | **gif-sticker-maker** | Convert photos (people, pets, objects, logos) into 4 animated GIF stickers with captions. Use when: user wants to create cartoon stickers, GIF expressions, emoji packs, animated... | 按需保留（多媒体生成与视频剪辑工具） |
| 2 | `gifgrep` | **gifgrep** | Search GIF providers with CLI/TUI, download results, and extract stills/sheets. | 按需保留（多媒体生成与视频剪辑工具） |
| 3 | `openai-image-gen` | **openai-image-gen** | Batch-generate images via OpenAI Images API. Random prompt sampler + `index.html` gallery. | 按需保留（多媒体生成与视频剪辑工具） |
| 4 | `openai-whisper` | **openai-whisper** | Local speech-to-text with the Whisper CLI (no API key). | 按需保留（多媒体生成与视频剪辑工具） |
| 5 | `openai-whisper-api` | **openai-whisper-api** | Transcribe audio via OpenAI Audio Transcriptions API (Whisper). | 按需保留（多媒体生成与视频剪辑工具） |
| 6 | `openstoryline-install` | **openstoryline-install** | Install, configure, and start FireRed-OpenStoryline from source on a local machine. Use when a user asks to set up OpenStoryline, troubleshoot installation, download required re... | 按需保留（多媒体生成与视频剪辑工具） |
| 7 | `openstoryline-use` | **openstoryline-use** | Use this skill when OpenStoryline is already installed and the user wants to start the local MCP/Web services, create or continue a session, send editing instructions, perform m... | 按需保留（多媒体生成与视频剪辑工具） |
| 8 | `sag` | **sag** | ElevenLabs text-to-speech with mac-style say UX. | 按需保留（多媒体生成与视频剪辑工具） |
| 9 | `seedance` | **seedance** | Generate AI videos using Volcengine Seedance model. Supports text-to-video (T2V), image-to-video (I2V), and audio-synced video generation. Use this skill when the user wants to ... | 按需保留（多媒体生成与视频剪辑工具） |
| 10 | `songsee` | **songsee** | Generate spectrograms and feature-panel visualizations from audio with the songsee CLI. | 按需保留（多媒体生成与视频剪辑工具） |
| 11 | `video-frames` | **video-frames** | Extract frames or short clips from videos using ffmpeg. | 按需保留（多媒体生成与视频剪辑工具） |
| 12 | `zenstudio` | **zenstudio** | ZenStudio 官方 AI 内容创作 CLI 工具 (zencli)。支持 AI 生图、AI 生视频、项目管理、资产库、媒资管理、无限画布、文件上传下载等。Use when user asks to generate images, generate videos, manage projects, upload files, download a... | 按需保留（多媒体生成与视频剪辑工具） |


### 9. 邮件收发与即时通讯（共 6 个）

| 序号 | 目录名称 (Folder) | 技能标识 (Skill Name) | 核心作用与使用场景 (Purpose & Description) | 状态 / 精简建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `agent-mail` | **agentmail** | Email inbox for AI agents. Check messages, send emails, and communicate via your own @agentmail.to address. | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |
| 2 | `email-skill` | **email-skill** | Email management and automation. Send, read, search, and organize emails across multiple providers. | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |
| 3 | `himalaya` | **himalaya** | CLI to manage emails via IMAP/SMTP. Use `himalaya` to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message co... | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |
| 4 | `imap-smtp-email` | **imap-smtp-email** | Read and send email via IMAP/SMTP. Check for new/unread messages, fetch content, search mailboxes, mark as read/unread, and send emails with attachments. Works with any IMAP/SMT... | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |
| 5 | `wacli` | **wacli** | Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI (not for normal user chats). | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |
| 6 | `workbuddy-channel-setup` | **workbuddy-channel-setup** | Automate WorkBuddy channel integration setup using playwright-cli. Supports Feishu and QQ Bot channels. Creates apps, configures bot capabilities, permissions, event subscriptio... | 建议精简（邮箱工具较多，可保留 1-2 个通用型即可） |

