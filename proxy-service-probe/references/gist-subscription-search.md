# GitHub Gist 代理订阅搜索与节点提取技术规范 (gist-subscription-search)

本规范详细说明从 GitHub Gist 检索代理订阅、通过方案 B (Fastly CDN Raw 免控直链) 提取节点、执行时效性衰减过滤以及单源垃圾熔断的技术机制。

---

## 1. 核心定位与并列架构

GitHub Gist 与空间测绘引擎（FoFa / 360 Quake）在 `proxy-service-probe` 中**处于同等重要的第一类数据源地位**：

| 数据源类型 | 引擎标识 | 数据特征 | 核心优势 |
| :--- | :--- | :--- | :--- |
| **空间测绘 (FoFa)** | `fofa` | Web 服务器响应特征 (反代/计量/Header) | 直连全球公网商用面板与订阅转换端点 |
| **空间测绘 (360 Quake)** | `quake` | 资产空间扫描、响应报文匹配 | 中文语境机场资产覆盖广，支持精准字段过滤 |
| **代码片段 (GitHub Gist)** | `gist` | 开发者、自动化机器人清洗推送的 **CDN 发布点** | **零成本、免 Token、极高时效**；直连商用机场订阅直链与清洗后的成品配置 |

---

## 2. 方案 B：Fastly CDN Raw 直链免控拉取机制

### 2.1 为什么采用方案 B？
1. **彻底摆脱 GitHub 官方 API 限制**：
   - GitHub REST API 与 GraphQL API 均未提供 `/search/gists` 端点；
   - 官方 API 对未认证请求有严格的 60 次/小时限制，即使配置 PAT 也受限于 5000 次/小时。
2. **Fastly CDN 高速直连**：
   - GitHub Gist 每一个文件均实时同步至 `https://gist.githubusercontent.com/{username}/{gist_id}/raw/...`；
   - Fastly CDN 具备全球多节点加速、无身份认证要求、无 API 频控配额，下载吞吐极大且免受 GitHub WAF 风控影响。

### 2.2 两阶段解耦流程
```
[阶段一: 定向低频检索]
用户指令 -> gist.github.com/search?q={query}&s=updated&o=desc
         -> 解析出时效合规的前 N 条 Gist 卡片 (默认 20 条，最近 48 小时内)
               │
               ▼
[阶段二: 方案B CDN 高并发拉取]
各 Gist 卡片 -> 提取页面内全部 Raw 文件直链 (gist.githubusercontent.com)
            -> ThreadPoolExecutor 并发下载
            -> 识别多格式节点 (YAML / JSON / Base64) 与 二级机场订阅 (subscribes.txt)
            -> 单源 > 200 节点自动熔断丢弃
            -> 统一指纹去重与协议顺位排序导出
```

---

## 3. 预设查询语法矩阵 (Preset Queries)

系统内置经过高频存活率实测校准的 6 大预设语法：

| 预设标识 (`--preset`) | 内部查询语法 | 命中目标与特征 |
| :--- | :--- | :--- |
| **`residential`**<br>*(官方优先主力，默认)*<br>*(别名: `isp`, `home`)* | `filename:yaml "ISP" proxies`<br>`filename:yaml "Hinet" proxies`<br>`filename:yaml "HKT" proxies`<br>`filename:yaml "家宽" proxies`<br>`filename:yaml "住宅" proxies`<br>`filename:txt "subscribe?token=" "ISP"`<br>`filename:txt "subscribe?token=" "Hinet"` | **多源定向聚合（默认）**：多路并发抓取包含商用家宽、原生双 ISP、知名落地运营商（Hinet/HKT）的最新高质量配置与直链订阅，去重并按最新更新时间倒序呈现前 20 条 |
| **`recommended`**<br>*(通用双源)* | `filename:yaml proxies` +<br>`filename:txt "subscribe?token="` | **双源并进**：同时抓取最新有效通用 Clash YAML 与商用机场直连 Token 订阅，智能去重并按更新时间呈现 |
| **`subs`**<br>*(商用机场直链金矿)* | `filename:txt "subscribe?token="` | **独立挖掘（可单独调用）**：专门检索包含商用面板 `subscribe?token=` 的直连订阅文件列表 |
| **`clash`** | `filename:yaml proxies` | 单独检索最新 Clash/Mihomo YAML 配置文件 |
| **`singbox`** | `filename:json "outbounds" "vless"` | 最新 sing-box 1.8+ 出站配置，含 VLESS Reality |
| **`hy2`** | `filename:yaml "hysteria2"` | 针对 Hysteria 2 极速专线节点配置专项检索 |
| **`base64`** | `filename:txt "vmess://" OR "vless://"` | 经典 Base64 节点分享列表 |
| **`comprehensive`** | `filename:yaml OR filename:json "proxies:" OR "outbounds"` | 全格式综合检索 |

---

## 4. 防污染与时效熔断契约

1. **时效性衰减过滤 (`--max-age-hours`, 默认 48.0 小时)**：
   - 检索时强制携带 `&s=updated&o=desc`；
   - 本地自动解析 `<relative-time datetime="...">`；
   - 超过 48 小时的 Gist 立即剔除，且自动触发后续分页提前截断，杜绝历史死节点。
2. **单源超量垃圾源熔断 (`--max-nodes-per-sub`, 默认 200 个节点)**：
   - 单个 Gist 文件或二级订阅内解析出的节点数若超过 200，系统判定为公网爬虫堆叠的低质死节点源，**直接丢弃**，不参与后续测活。
3. **嵌套二级订阅平滑防雪崩**：
   - 当遇到 `subscribes.txt` 等直链列表时，单 Gist 限制最多递归拉取前 5 条订阅直链，防止恶意循环嵌套或请求雪崩。

---

## 5. 配置文件契约 `gist_config.json`

位于技能根目录下（`gist_config.json`）：
```json
{
  "max_age_hours": 48,
  "default_targets": 20,
  "max_nodes_per_subscription": 200,
  "proxy": "http://127.0.0.1:3067",
  "timeout": 12,
  "default_query": "filename:yaml proxies"
}
```
*注：若 `proxy` 为空，系统自动尝试复用 `fofa_config.json` 中的代理地址；支持环境变量 `GIST_PROXY`、`GIST_MAX_AGE_HOURS`、`GIST_DEFAULT_TARGETS` 进行运行时覆盖。*

---

## 6. CLI 命令行大全

```bash
# 1. 默认官方推荐搜索 (优先检索家宽/双ISP/高纯净度订阅，抓取最新 20 条有效 Gist 并提取节点)
python scripts/gist_search.py --output gist_proxies.yaml

# 2. 挖掘商用机场直连 Token 订阅
python scripts/gist_search.py --preset subs --output subs_nodes.yaml

# 3. 搜索特定协议 (如 Hysteria 2 专线)
python scripts/gist_search.py --preset hy2 -o hy2_nodes.yaml

# 4. 仅测试检索目标 Gist (干跑模式，展示时效与文件列表)
python scripts/gist_search.py --dry-run-targets

# 5. 指定时效上限为最近 24 小时、单源上限 100 节点
python scripts/gist_search.py --max-age-hours 24 --max-nodes-per-sub 100 -o fresh.yaml

# 6. 一键检索并直接联动全量服务能力测试 (Playwright YouTube实播 + AI全通 + 4站免盾 + 导出)
python scripts/gist_search.py --probe --output final.yaml

# 7. 检索、测试并直接合流并入既有目标底库配置
python scripts/gist_search.py --probe --merge-into base_template.yaml

# 8. 通过主流水线 probe_services.py 直接指定 Gist 输入源 (默认优先 residential 家宽/优质过盾)
python scripts/probe_services.py --input gist:residential --output final.yaml
python scripts/probe_services.py --input gist:subs --output final.yaml

# 9. 通过通用搜索工具 fofa_search.py 指定 Gist 引擎
python scripts/fofa_search.py --engine gist --preset residential -o gist_nodes.yaml
```
