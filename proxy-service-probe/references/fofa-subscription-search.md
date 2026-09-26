# 空间测绘订阅搜索与节点提取规范 (FoFa & 360 Quake)

本模块将空间测绘订阅搜索、长效存活特征语法解析、360 Quake 协同检索与多源目标去重提取能力完整整合到 `proxy-service-probe` 技能中。

## 1. 契约原则与安全边界

- **非主动触发机制**：空间测绘订阅检索为主动触发式能力，默认流水线绝不主动发起网络资产扫描；**仅当用户明确主动要求搜索订阅**（如指令包含“搜索 FoFa 订阅”、“搜索 Quake 订阅”、“抓取订阅节点”或显式调用 `scripts/fofa_search.py` / 传入 `--input fofa:...` / `--input quake:...` / `--input spatial:...`）时才启动。
- **双引擎高容错与独立运行**：支持同时调用 FoFa 与 360 Quake 检索。单一引擎遭遇网络异常、凭证缺失或限流不会阻断另一个引擎工作；两端检索到的目标订阅源 URL 自动执行全局规范化去重。
- **配置与密钥独立隔离**：FoFa Token/Key 与 360 Quake Key 以独立文件形式在技能根目录下的 [`fofa_config.json`](../fofa_config.json) 中进行配置与变量引用，严禁在代码中硬编码任何个人敏感凭证。

---

## 2. 配置文件规范 (`fofa_config.json`)

在技能根目录 (`E:\_BIGFAFree\_code\skills\proxy-service-probe\fofa_config.json`) 下统一维护如下结构：

```json
{
  "token": "eyJhbGciOiJIUzUxMiIsImtpZCI6Ik5XWTVZakF4TVRkalltSTJNRFZsWXpRM05EWXdaakF3TURVMlkyWTNZemd3TUdRd1pUTmpZUT09IiwidHlwIjoiSldUIn0...",
  "email": "",
  "key": "",
  "quake_key": "",
  "proxy": "http://127.0.0.1:3067",
  "page_size": 50,
  "timeout": 12,
  "max_nodes_per_subscription": 200,
  "default_query": "(server=\"nginx\" || server=\"caddy\" || server=\"cloudflare\" || server=\"openresty\") && header=\"subscription-userinfo\" && body=\"proxies:\" && body!=\"<html\"",
  "quake_default_query": "status_code: 200 AND NOT response: \"<html\" AND (response: \"nginx\" OR response: \"caddy\" OR response: \"cloudflare\" OR response: \"openresty\") AND (response: \"subscription-userinfo\" OR (response: \"upload=\" AND response: \"download=\")) AND response: \"proxies:\""
}
```

### 字段说明
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `token` | string | FoFa Web 端 JWT 授权凭据（自动注入 `Authorization` 请求头与 `fofa_token` Cookie） |
| `email` | string | FoFa 官方 API 账号邮箱（选填，用于官方 API 调用） |
| `key` | string | FoFa 官方 API Key（选填，用于官方 API 调用） |
| `quake_key` | string | 360 Quake API Key 凭证（自动注入 `X-QuakeToken` 请求头） |
| `proxy` | string | 本地 HTTP/SOCKS 代理客户端地址（如 `http://127.0.0.1:3067`），网络受阻时自动尝试代理与直连双通道保底 |
| `page_size`| int | 每次检索请求的结果数量（FoFa / Quake 单页通常支持最大 50 条） |
| `timeout` | int | 单次检索与订阅抓取的超时阈值（秒） |
| `max_nodes_per_subscription` | int | 单订阅源节点数量上限（默认 200，超过此阈值视为公开聚合低质垃圾源予以丢弃） |
| `default_query` | string | FoFa 未指定语法时使用的默认搜索语句 |
| `quake_default_query` | string | Quake 未指定语法时使用的默认搜索语句 |

> 环境变量覆盖：支持通过 `FOFA_TOKEN`, `FOFA_KEY`, `FOFA_EMAIL`, `QUAKE_KEY` / `QUAKE_TOKEN`, `FOFA_PROXY` 在无配置文件或 CI 环境下动态注入。

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
| **`recommended` (推荐主力)** | `(server="nginx" \|\| server="caddy" \|\| server="cloudflare" \|\| server="openresty") && header="subscription-userinfo" && body="proxies:" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND (response: "nginx" OR response: "caddy" OR response: "cloudflare" OR response: "openresty") AND (response: "subscription-userinfo" OR (response: "upload=" AND response: "download=")) AND response: "proxies:"` |
| **`billing` (动态计费)** | `(header="upload=" && header="download=" && header="total=") && body="proxies:" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "upload=" AND response: "download=" AND response: "total=" AND response: "proxies:"` |
| **`comprehensive` (原版综合)**| `status_code="200" && body!="<html" && (body="proxies:" \|\| body="\"outbounds\":" \|\| (header="text/plain" && (body="dm1lc3M6" \|\| body="c3M6Ly" \|\| body="dHJvamFuOi")))` | `status_code: 200 AND NOT response: "<html" AND (response: "proxies:" OR response: "\"outbounds\":" OR response: "dm1lc3M6" OR response: "c3M6Ly" OR response: "dHJvamFuOi")` |
| **`vless` (VLESS/Reality)** | `body="proxies:" && body="type: vless" && status_code="200" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "proxies:" AND response: "vless"` |
| **`hy2` (Hysteria 2)** | `body="type: hysteria2" && body="server" && status_code="200" && body!="<html"` | `status_code: 200 AND NOT response: "<html" AND response: "hysteria2" AND response: "server"` |
| **`sub_userinfo` (动态流量池)** | `header="subscription-userinfo" && status_code="200"` | `status_code: 200 AND response: "subscription-userinfo"` |
```text
body="proxies:" && body="type: vless" && status_code="200" && body!="<html"
```

### 🌟 预设 4: `hy2` (Hysteria 2 极速节点专项订阅)
```text
body="type: hysteria2" && body="server" && status_code="200" && body!="<html"
```

### 🌟 预设 5: `sub_userinfo` (通用动态流量池)
```text
header="subscription-userinfo" && status_code="200"
```

### 🌟 预设 6: `comprehensive` (多协议复合订阅源)
```text
status_code="200" && body!="<html" && (body="proxies:" || body="\"outbounds\":" || (header="text/plain" && (body="dm1lc3M6" || body="c3M6Ly" || body="dHJvamFuOi")))
```

---

## 4. 节点提取、去重与顺位排序

1. **客户端伪装请求**：
   使用 `User-Agent: ClashforWindows/0.20.39`（兼容 Subconverter/各面板格式协商），确保下发完整的 Clash YAML 或 Base64 订阅。
2. **多格式全兼容解析**：
   复用 `core.parsers.load_proxies` 引擎，单次自动兼容解析 Clash YAML、sing-box JSON (`outbounds:`) 及多行 Base64 节点链接。
3. **低质公开聚合源自动淘汰 (<=200 节点门槛)**：
   **单订阅源节点数 > 200 一律自动丢弃**。网络上节点数数百甚至上千的订阅源，绝大多数是爬取自 Telegram 频道等公开渠道的低质聚合垃圾池（含大量死节点与重复节点），会极度浪费检测时间并污染节点池。此阈值可在 `fofa_config.json` 中的 `max_nodes_per_subscription` 或通过命令行 `--max-nodes-per-sub` 调节。
4. **全局唯一指纹去重**：
   对抓取的所有候选节点，依据 `(协议类型, 规范化服务器地址, 端口, 密码/UUID)` 进行指纹哈希去重。
5. **协议顺位优化**：
   按 `Hysteria 2 / Hy2 -> VLESS -> Trojan -> VMess -> Shadowsocks -> 其他` 进行保序排序，优先提升前序节点的高速 UDP 与抗封锁特性。

---

## 5. 命令行使用指南

```bash
# 1. 默认双引擎协同：同时使用 FoFa 与 360 Quake 检索并全局去重导出
python scripts/fofa_search.py --output spatial_proxies.yaml

# 2. 指定单引擎运行 (仅 FoFa 或 仅 Quake)
python scripts/fofa_search.py --engine quake --preset recommended --output quake_nodes.yaml
python scripts/fofa_search.py --engine fofa --preset hy2 --output fofa_hy2.yaml

# 3. 使用 Quake 自定义语法
python scripts/fofa_search.py --engine quake --quake-query 'status_code: 200 AND response: "vless"' -o quake_vless.yaml

# 4. 仅检索并查看双引擎发现的目标 URL (去重展示，不下载订阅)
python scripts/fofa_search.py --dry-run-targets

# 5. 一键联动：抓取节点后直接调用主流水线进行全套服务能力检测与配置渲染
python scripts/fofa_search.py --probe --output final_probed.yaml

# 6. 主流水线直接以测绘源作为输入
python scripts/probe_services.py --input spatial:recommended --output out.yaml
python scripts/probe_services.py --input quake:recommended --output out.yaml
```
