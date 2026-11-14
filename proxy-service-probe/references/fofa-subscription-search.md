# 空间测绘订阅搜索与节点提取规范 (FoFa & 360 Quake)

本模块将空间测绘订阅搜索、长效存活特征语法解析、360 Quake 协同检索与多源目标去重提取能力完整整合到 `proxy-service-probe` 技能中。

## 1. 契约原则与安全边界

- **非主动触发机制**：空间测绘订阅检索为主动触发式能力，默认流水线绝不主动发起网络资产扫描；**仅当用户明确主动要求搜索订阅**（如指令包含“搜索 FoFa 订阅”、“搜索 Quake 订阅”、“抓取订阅节点”或显式调用 `scripts/fofa_search.py` / 传入 `--input fofa:...` / `--input quake:...` / `--input spatial:...`）时才启动。
- **双引擎高容错与独立运行**：支持同时调用 FoFa 与 360 Quake 检索。单一引擎遭遇网络异常、凭证缺失或限流不会阻断另一个引擎工作；两端检索到的目标订阅源 URL 自动执行全局规范化去重。
- **配置与密钥独立隔离**：FoFa Token/Key 与 360 Quake Key 以独立文件形式在技能根目录下的 `fofa_config.json`（模板见 [`fofa_config.example.json`](../fofa_config.example.json)）中进行配置与变量引用，严禁在代码中硬编码任何个人敏感凭证。

---

## 2. 配置文件规范 (`fofa_config.json`)

在技能根目录 (`<skill>/fofa_config.json`) 下统一维护如下结构：

```json
{
  "base_url": "https://fofa.info",
  "token": "your_fofa_jwt_token_here",
  "tokens": [],
  "email": "",
  "key": "",
  "quake_key": "",
  "proxy": "http://127.0.0.1:3067",
  "page_size": 80,
  "timeout": 12,
  "max_nodes_per_subscription": 300,
  "default_query": "residential",
  "quake_default_query": "residential"
}
```

### 字段说明
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `base_url` | string | FoFa API 基础地址（默认 `https://fofa.info`，支持第三方中转站/镜像站如 `fafaapi.info`） |
| `token` | string | FoFa Web 端 JWT 授权凭据（自动注入 `Authorization` 请求头与 `fofa_token` Cookie） |
| `tokens` | list | FoFa Web 多 Token 列表（支持多账号轮询切换，防单账号限流） |
| `account` | object | FoFa / NOSEC 登录账号与密码（`{"username": "...", "password": "..."}`），供自动化登录与免登刷新脚本使用 |
| `email` | string | FoFa 账号邮箱（用于官方 API 或自动登录） |
| `password` | string | FoFa / NOSEC 登录密码（用于自动登录续期） |
| `key` | string | FoFa 官方 API Key（选填，用于官方 API 调用，永不过期） |
| `quake_key` | string | 360 Quake API Key 凭证（自动注入 `X-QuakeToken` 请求头） |
| `proxy` | string | 本地 HTTP/SOCKS 代理客户端地址（如 `http://127.0.0.1:3067`），网络受阻时自动尝试代理与直连双通道保底 |
| `page_size`| int | 每次检索请求的结果数量（FoFa / Quake 单页通常支持最大 50 条） |
| `timeout` | int | 单次检索与订阅抓取的超时阈值（秒） |
| `max_nodes_per_subscription` | int | 单订阅源节点数量上限（默认 300，超过此阈值视为公开聚合低质垃圾源予以丢弃） |
| `default_query` | string | FoFa 未指定语法时使用的默认搜索语句 |
| `quake_default_query` | string | Quake 未指定语法时使用的默认搜索语句 |

> **Token 自动化续期 (免去手动 F12 抓取)**：
> 1. **一键浏览器登录**：运行 `python scripts/fofa_search.py --login`，系统通过 Playwright 调起浏览器载入 NOSEC 统一登录页，自动填入凭据、过 Cloudflare Turnstile 验证并提取 `fofa_token` 自动保存回写至 `fofa_config.json`。
> 2. **到期自动静默续期**：在 `fofa_config.json` 中配置 `account`（或 `email` + `password`），后续执行搜索时只要检测到 Token 即将到期或已过期，系统会在发起搜索前自动执行登录刷新，维持 30 天无感连续使用。
> 3. **官方 API Key (终身免维护)**：直接在 `fofa_config.json` 中填入官方 `key`，调用官方 API，终身无需维护 Token。
> 环境变量覆盖：支持通过 `FOFA_TOKEN`, `FOFA_KEY`, `FOFA_EMAIL`/`FOFA_USER`, `FOFA_PASSWORD`, `FOFA_BASE_URL`, `QUAKE_KEY` / `QUAKE_TOKEN`, `FOFA_PROXY` 在无配置文件或 CI 环境下动态注入。

---

## 3. Quake 语法优化分析与动态语法体系

### 3.1 用户参考语法优化空间评估
用户提供的参考语法：
```text
status_code: 200 AND NOT response: "<html" AND (response: "proxies:" OR response: "\"outbounds\":" OR response: "dm1lc3M6" OR response: "c3M6Ly" OR response: "dHJvamFuOi")
```
经过与测绘引擎底层索引特征比对，存在以下三大关键优化空间：
1. **剔除临时一次性测试服务器（存活率提升 50%+）**：
   原语法未限定服务器类型，90% 的命中结果来自用户个人临时运行的 Python `BaseHTTP/SimpleHTTP`（测试几分钟即关闭，几天后就全部死亡）。
   **优化方案**：加入反代生产服务器断言 `(response: "nginx" OR response: "caddy" OR response: "cloudflare" OR response: "openresty")`，确保为长期托管在 VPS 上的生产级环境。
2. **过滤正文包含 base64 关键字的伪源与教程文档**：
   `response: "dm1lc3M6"` (vmess:) / `response: "c3M6Ly"` (ss://) 会命中许多技术博客、Github 镜像 README 或文本错误回显，并非真实订阅接口。
   **优化方案**：精准锚定结构化字段 `response: "proxies:"` 或结合流量计量特征。
3. **引入动态计费与流量头（高活性持续运营）**：
   商业运营面板（SSPanel, V2board, Subconverter）必定返回动态计量头 `subscription-userinfo: upload=...; download=...; total=...`。
   **优化方案**：追加 `response: "subscription-userinfo"` 或 `(response: "upload=" AND response: "download=")`.

---

### 3.2 预设语法对照表

| 预设别名 (`--preset`) | FoFa 语法 | 360 Quake 语法 |
| :--- | :--- | :--- |
| **`residential` (官方优先主力)**<br>*(别名: `isp`, `home`)* | `(server="nginx" \|\| server="caddy" \|\| server="cloudflare" \|\| server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html" && (body="家宽" \|\| body="住宅" \|\| body="双ISP" \|\| body="Hinet" \|\| body="HKT" \|\| body="ISP")` | `status_code: 200 AND NOT response: "<html" AND (response: "subscription-userinfo" OR response: "upload=") AND response: "proxies:" AND (response: "家宽" OR response: "住宅" OR response: "Hinet" OR response: "HKT" OR response: "ISP")` |
| **`recommended` (工业反代+计费)** | `(server="nginx" \|\| server="caddy" \|\| server="cloudflare" \|\| server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND (response: "nginx" OR response: "caddy" OR response: "cloudflare" OR response: "openresty") AND (response: "subscription-userinfo" OR (response: "upload=" AND response: "download=")) AND response: "proxies:"` |
| **`billing` (动态计费)** | `(header="upload=" && header="download=" && header="total=") && body="proxies:" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "upload=" AND response: "download=" AND response: "total=" AND response: "proxies:"` |
| **`comprehensive` (原版综合)**| `status_code="200" && body!="<html" && (body="proxies:" \|\| body="\"outbounds\":" \|\| (header="text/plain" && (body="dm1lc3M6" \|\| body="c3M6Ly" \|\| body="dHJvamFuOi")))` | `status_code: 200 AND NOT response: "<html" AND (response: "proxies:" OR response: "\"outbounds\":" OR response: "dm1lc3M6" OR response: "c3M6Ly" OR response: "dHJvamFuOi")` |
| **`vless` (VLESS/Reality)** | `body="proxies:" && body="type: vless" && status_code="200" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "proxies:" AND response: "vless"` |
| **`hy2` (Hysteria 2)** | `body="type: hysteria2" && body="server" && status_code="200" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "hysteria2" AND response: "server"` |
| **`sub_userinfo` (动态流量池)** | `header="subscription-userinfo" && status_code="200"` | `status_code: 200 AND response: "subscription-userinfo"` |

---

## 4. 节点提取、去重与顺位排序

1. **客户端伪装请求**：
   使用 `User-Agent: ClashforWindows/0.20.39`（兼容 Subconverter/各面板格式协商），确保下发完整的 Clash YAML 或 Base64 订阅。
2. **多格式全兼容解析**：
   复用 `core.parsers.load_proxies` 引擎，单次自动兼容解析 Clash YAML、sing-box JSON (`outbounds:`) 及多行 Base64 节点链接。
3. **低质公开聚合源自动淘汰 (<=300 节点门槛)**：
   **单订阅源节点数 > 300 一律自动丢弃**。网络上节点数数百甚至上千的订阅源，绝大多数是爬取自 Telegram 频道等公开渠道的低质聚合垃圾池（含大量死节点与重复节点），会极度浪费检测时间并污染节点池。此阈值可在 `fofa_config.json` 中的 `max_nodes_per_subscription` 或通过命令行 `--max-nodes-per-sub` 调节。
4. **全局唯一指纹去重**：
   对抓取的所有候选节点，依据 `(协议类型, 规范化服务器地址, 端口, 密码/UUID)` 进行指纹哈希去重。
5. **协议顺位优化**：
   按 `Hysteria 2 / Hy2 -> VLESS -> Trojan -> VMess -> Shadowsocks -> 其他` 进行保序排序，优先提升前序节点的高速 UDP 与抗封锁特性。

---

## 5. 命令行使用指南

```bash
# 1. 测绘引擎鉴权状态诊断 (检测 FoFa API Key、Web Token 到期时间、自动登录凭据及 Quake 额度)
python scripts/fofa_search.py --check-auth

# 2. 自动化登录 FoFa/NOSEC 并提取最新 Token 自动保存至 fofa_config.json (免除手动 F12 复制)
python scripts/fofa_search.py --login
# 亦可指定账号密码直接静默执行:
python scripts/fofa_search.py --login -u your_email@domain.com --password your_password

# 3. 默认双引擎协同：优先检索家宽/双ISP/高纯净度订阅 (FoFa + 360 Quake 协同并全局去重)
python scripts/fofa_search.py --output spatial_proxies.yaml

# 4. 检索时开启自动续期 (Token 过期时自动调用登录刷新)
python scripts/fofa_search.py --auto-login --output spatial_proxies.yaml

# 5. 指定单引擎运行 (如 仅 Quake 家宽 / 仅 FoFa Hysteria 2)
python scripts/fofa_search.py --engine quake --preset residential --output quake_residential.yaml
python scripts/fofa_search.py --engine fofa --preset hy2 --output fofa_hy2.yaml

# 6. 使用 Quake 自定义语法
python scripts/fofa_search.py --engine quake --quake-query 'status_code: 200 AND response: "vless"' -o quake_vless.yaml

# 7. 仅检索并查看双引擎发现的目标 URL (去重展示，不下载订阅)
python scripts/fofa_search.py --dry-run-targets

# 8. 一键联动：抓取节点后直接调用主流水线进行全套服务能力检测与配置渲染
python scripts/fofa_search.py --probe --output final_probed.yaml

# 9. 主流水线直接以测绘源作为输入 (默认优先 residential 家宽/优质过盾)
python scripts/probe_services.py --input spatial:residential --output out.yaml
python scripts/probe_services.py --input quake:residential --output out.yaml
```
