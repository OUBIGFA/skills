# GitHub Gist 订阅搜索与提取功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现与 FoFa / 360 Quake 并列的 GitHub Gist 代理订阅搜索与提取引擎，采用 CDN Raw 免控拉取方案（方案B），默认抓取 20 条最新有效目标，过滤超过 200 节点的超量聚合源，并与 `probe_services.py` 完整联动。

**Architecture:** 
构建 `core.gist` 底层引擎，负责 Web 定向检索（`&s=updated&o=desc`）、时效校验（默认 48h 内）、文件发现与 Fastly CDN Raw 免控并发拉取；集成至 `core.parsers`（支持 `gist:` 输入前缀）；扩展 `fofa_search.py`（支持 `--engine gist` 及多源并列）并提供独立 `gist_search.py` CLI；更新文档与单元测试。

**Tech Stack:** Python 3, requests, PyYAML, BeautifulSoup/re, unittest, Mihomo/sing-box runner

---

## Global Constraints

- **免控拉取契约**：内容拉取阶段一律采用方案B（GitHub Fastly CDN Raw 直链：`https://gist.githubusercontent.com/{user}/{gist_id}/raw/...`），不强制要求 GitHub PAT，零风控、免 Token 频率限制。
- **默认容量与时效契约**：默认抓取 20 条最新且更新时间在 48 小时内的有效目标（`max_targets=20`）。
- **防污染熔断契约**：单源解析节点数 > 200 时直接丢弃，严防低质死节点与超量公开聚合源干扰。
- **编码与端口契约**：Windows 下严格处理 UTF-8 编码与 emoji（使用 replace/ignore）；网络请求严格走环回端口或配置代理，不改动系统代理注册表。

---

### Task 1: 配置文件与核心数据结构 (`gist_config.json` 与 `scripts/core/gist.py` 基础)

**Files:**
- Create: `gist_config.json`
- Create: `scripts/core/gist.py`
- Create: `tests/test_gist_search.py`

**Interfaces:**
- Consumes: `core.parsers.load_proxies`, `core.parsers.UA`
- Produces: `get_default_gist_config_path()`, `load_gist_config()`, `resolve_gist_query()`, `PRESET_GIST_QUERIES`

- [ ] **Step 1: 编写配置与预设语法的失败测试**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 创建 `gist_config.json` 并实现 `core/gist.py` 的配置加载与预设解析**
- [ ] **Step 4: 运行测试验证通过**

---

### Task 2: Gist Web 搜索卡片解析、时效过滤与 CDN Raw 直链发现

**Files:**
- Modify: `scripts/core/gist.py`
- Modify: `tests/test_gist_search.py`

**Interfaces:**
- Consumes: `BeautifulSoup`/`re`, `requests`
- Produces: `search_gist_targets(query, max_targets=20, max_age_hours=48, ...) -> List[Dict[str, Any]]`

- [ ] **Step 1: 编写 HTML 卡片解析、时间戳计算与 Raw URL 提取的单元测试（含 48h 过滤）**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 在 `core/gist.py` 实现 `search_gist_targets`、`_parse_gist_search_html` 及 CDN Raw 直链转换**
- [ ] **Step 4: 运行测试验证通过**

---

### Task 3: 方案B CDN Raw 内容并发拉取、异构格式解析与 >200 节点熔断

**Files:**
- Modify: `scripts/core/gist.py`
- Modify: `tests/test_gist_search.py`

**Interfaces:**
- Consumes: `core.parsers.load_proxies`, `core.fofa.deduplicate_and_sort_proxies`
- Produces: `fetch_gist_nodes(targets, max_nodes_per_sub=200, ...) -> List[Dict[str, Any]]`, `search_and_fetch_gist_proxies(...)`

- [ ] **Step 1: 编写多文件 Raw 内容拉取、subscribes.txt 递归提取与 >200 熔断测试**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 在 `core/gist.py` 实现 `fetch_gist_nodes` 与二级订阅提取逻辑**
- [ ] **Step 4: 运行测试验证通过**

---

### Task 4: 与既有系统无缝集成 (`core/parsers.py`, `fofa_search.py`, `gist_search.py`)

**Files:**
- Modify: `scripts/core/parsers.py` (接入 `gist:` 与 `gist` 前缀)
- Modify: `scripts/fofa_search.py` (引擎选项增加 `gist`，多源协同)
- Create: `scripts/gist_search.py` (独立命令行入口，支持 `--probe` 与 `--merge-into`)
- Modify: `tests/test_gist_search.py`

**Interfaces:**
- Consumes: `core.parsers.load_proxies("gist:recommended")`
- Produces: `scripts/gist_search.py`, CLI 参数支持 `--engine gist`

- [ ] **Step 1: 编写 `load_proxies("gist")` 与 `fofa_search.py --engine gist` 的集成测试**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 修改 `core/parsers.py`、`fofa_search.py` 并创建 `scripts/gist_search.py`**
- [ ] **Step 4: 运行测试验证通过**

---

### Task 5: 文档、契约与端到端实测验证

**Files:**
- Create: `references/gist-subscription-search.md`
- Modify: `SKILL.md` (同步更新常用 CLI 与能力契约)

- [ ] **Step 1: 编写 `references/gist-subscription-search.md` 说明 Gist 搜索机制与参数用法**
- [ ] **Step 2: 更新 `SKILL.md` 的命令行与核心契约**
- [ ] **Step 3: 运行完整测试套件 `python -m unittest tests/test_gist_search.py tests/test_fofa_search.py`**
- [ ] **Step 4: 执行真实命令验证 `--dry-run-targets` 与节点提取**
