# 服务能力测试判据与规范

本文档详述各个测试维度的严格判据、请求端点、特征匹配规则、打标规范及淘汰机制。

---

## 1. 真实出口与 IP 属地检测 (IP Egress & Geolocation)

### 1.1 双栈出口与基线防污染
- **出口探测端点**：
  - IPv4: `https://api.ipify.org?format=json`, `https://ipv4.icanhazip.com`
  - IPv6: `https://api6.ipify.org?format=json`, `https://ipv6.icanhazip.com`
- **跑机基线出口（Runner Baseline）**：
  - 在探测任何节点前，必须先获取本地/跑机自身的直连公网出口 IP（`probe_egress(None)`）。
  - 若被测节点返回的出口 IP 与跑机自身直连出口一致（`runner_ip_match=True`），说明代理穿透失败或流量走直连泄露，判定为无效节点。
  - 在开启 TUN（如 Karing）的机器上，基线探测必须绑定物理网卡或走独立直连代理（`FREENODE_LOCAL_DIRECT_PROXY`），防止把系统全局代理的出口当作跑机基线。
- **出口稳定性（Stability）**：
  - 各项服务探测前后分别采集出口 IP。若前后出口 IP 不一致，标记为出口不稳定（漂移）。

### 1.2 Google 自身地区码判定 (Google Region - 最高优先级)
独立于任何第三方商用或公开 GeoIP 库，以 Google 官方服务对该 IP 的属地归因作为最终国别定性的第一依据：
- **第一来源（Gemini 页面）**：
  - 请求目标：`https://gemini.google.com/`
  - 匹配规则：
    1. 提取 ISO 3166-1 alpha-3 地区码：正则 `,2,1,200,\"([A-Z]{3})\"`（例如 `HKG` -> `HK`, `SGP` -> `SG`, `JPN` -> `JP`, `USA` -> `US`）。
    2. 提取 Gemini 服务可用性标志：正则 `\[45631641,null,(true|false|null)`。
- **第二来源（YouTube Premium 页面兜底）**：
  - 当 Gemini 页面无法读取时，请求 `https://www.youtube.com/premium` 作为兜底。
  - 必须同时存在 `"INNERTUBE_CONTEXT_GL":"([A-Za-z]{2})"` 与 `"countryCode":"([A-Za-z]{2})"` 且两者完全一致，才采纳为有效国家码（若二者不一致，说明属于 YouTube 默认 fallback，记为 `region_ambiguous` 不予采纳）。
- **送中判定（Sent-to-China）**：
  - 若 Google 地区码归因为 `CN` 或 `CHN`，说明该 IP 被 Google 识别为中国大陆出口。
  - 必须剥离该节点的 AI 解锁资格（`ai_supported=False`），并视策略进行送中隔离或淘汰。

### 1.3 多源 GeoIP 投票
当 Google 未给出有效国家码时，采用多源公网数据库进行投票：
- **数据源**：
  - `ipwhois`: `https://ipwho.is/{ip}`
  - `ipsb`: `https://api.ip.sb/geoip/{ip}`
  - `Net.Coffee`: `https://ip.net.coffee/api/ip/lookup/{ip}`
- **投票算法**：
  - `confirmed`：来源 >= 2 且全部一致（高置信度）。
  - `majority`：超过 50% 来源一致（中置信度）。
  - `conflict` / `insufficient`：存在冲突或数据不足（低置信度）。

### 1.4 IP 信誉与欺诈风险评估 (Net.Coffee)
- **Trust Score**：0-100 分。
  - `>= 75`：良好 (`good`)。
  - `45 - 74`：一般 (`moderate`)。
  - `< 45`：较差 (`poor`)。
- **属性标签（Flags）**：
  - `isResidential`（住宅家宽）
  - `is_datacenter`（机房/数据中心）
  - `is_vpn` / `is_proxy` / `is_tor`（VPN/代理/Tor出口）
  - `is_crawler` / `is_abuser`（爬虫/滥用记录）

---

## 2. AI 平台解锁检测 (AI Unlock)

三大主流平台独立检验，所有接口要求目标服务本身返回“地区允许”证据，杜绝因凭据失效或网络错误导致的误判。

| 平台 | 探测端点 | 判定依据 | 失败/封锁判定 |
|---|---|---|---|
| **ChatGPT (OpenAI)** | 1. 合规接口：`https://api.openai.com/compliance/cookie_requirements`<br>2. 状态接口：`https://ios.chat.openai.com/public-api/mobile/server_status/v1` (UA: `ChatGPT/1.2024.000`)<br>3. 模型接口：`https://api.openai.com/v1/models` | 合规接口返回 `200` 且正文含 `cookie_consent_required` 证明地区允许；且状态接口返回 `200` 或模型接口返回 `401`（未授权证明连通）即判定解锁。 | 合规接口返回 `403 unsupported_country_region_territory` 为地区封锁。 |
| **Claude (Anthropic)** | 模型端点：`https://api.anthropic.com/v1/models` | 返回 `401`（Unauthorized）或 `200` 即判定解锁（证明成功到达模型网关）。 | 返回 `403` 且正文含 `Request not allowed` 判定为地区封锁。 |
| **Gemini (Google)** | 页面端点：`https://gemini.google.com/` | 正文解析到标志 `[45631641,null,true]` 且地区非大陆（非 `CN`/`CHN`）。 | 正文含可用性标志为 `false`、正文包含 `not supported in your country` 或地区码为 `CN`。 |

- **AI 三大全通条件**：
  出口稳定 + 真实出口非送中 + ChatGPT 通过 + Claude 通过 + Gemini 通过。
  满足此条件的节点获赠 **`❇️`** 徽章。

---

## 3. YouTube 免登录实播检测 (Anonymous YouTube Playback)

非普通 API 连通性测试，而是验证无 Cookie、无登录状态下的真实媒体流播放与抗机器人风控能力。

- **浏览器环境**：Playwright 驱动完整版 Chromium（`channel="chromium"`），关闭自动化特征（`--disable-blink-features=AutomationControlled`，`--disable-quic`，locale: `en-US`）。
- **测试样本视频**：`M7lc1UVf-VE`, `aqz-KE-bpKQ`, `jNQXAC9IVRw`。
- **HTML5 播放观察者（Playback Observer）**：
  - 动态监听 `<video>` 元素的播放事件与时间戳更新。
  - **达标条件**：`currentTime` 连续播放累计时长 `>= 10.0` 秒，且非停滞缓冲（`readyState >= 3`）。
  - **风控与限制判定**：
    - `bot_required`：页面提示 "Sign in to confirm you’re not a bot" 或出现 Turnstile/Captcha 人机验证。
    - `sign_in_required`：需要登录才能观看。
    - `rate_limited`：429 或流量限制。
    - `playback_start_failed`：无法起播。
- **双向出口复核（Double Egress Check）**：
  - 播放前：浏览器 Context 访问出口检测接口，确认当前浏览器 IP 确实等于被测节点 IP。
  - 播放后：再次核对浏览器出口 IP，若前后不一致或与节点 IP 不符，判定为 `browser_egress_unverified`，防止流量被本地直连或分流绕过。
- **通过标准**：至少成功实播通过 **2 个** 独立样本视频。

---

## 4. 目标网站免盾 / 过盾检测 (Shield Probe)

测试节点在访问主流云安全防御目标时的免质询/过盾能力。

- **监控目标**：
  1. `cloudflare`: `https://www.cloudflare.com/`（弱挑战首页）
  2. `chatgpt`: `https://chatgpt.com/`
  3. `claude`: `https://www.anthropic.com/`
  4. `gemini`: `https://gemini.google.com/`
- **质询识别特征（Challenge Markers）**：
  - 响应头 `cf-mitigated: challenge`
  - 页面正文特征：`just a moment`, `checking your browser`, `verify you are human`, `cf-chl-`, `checking if the site connection is secure`, `请完成安全验证` 等。
  - 状态码 `403`, `451`, `1020` 等阻断码。
- **执行阶段**：
  - **HTTP 初查**：使用 Chrome 140 仿真头请求各目标，快速分类 `passed`、`challenge`、`blocked`。
  - **浏览器复核**：针对重点节点或全量节点，在 Playwright Chromium 中加载页面并等待最多 8 秒，验证质询是否能自动通过。
- **免盾判定规则（`shield_passed`）**：
  4 站浏览器观测齐全，且**至多 1 站**遇到挑战（且能自动解除通过），其余全部无阻断通过，方可判定为“规定网站免盾”。

---

## 5. 国际流媒体与带宽防断流检测

### 5.1 国际流媒体
- **Netflix (奈飞)**：
  - 请求非自制剧页面 `https://www.netflix.com/title/81280792` 或 `https://www.netflix.com/title/80018499`。
  - 状态码返回 `200` 判定为解锁；返回 403/404/重定向登录判定为仅解锁自制剧或未解锁。
- **Disney+ (迪士尼)**：
  - 请求 `https://www.disneyplus.com/`。
  - 状态码返回 `200`, `301`, `302` 且页面正文不含 `not available` 或 `unsupported` 判定为解锁。

### 5.2 3 秒流式下载带宽与断流淘汰 (Stall Check)
- **测速目标**：
  - `https://speed.cloudflare.com/__down?bytes=10000000`
  - `https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg`（Range: 0-10485759）
- **测速窗**：固定 3.0 秒流式下载。
- **断流淘汰标准**：
  - 累计传输字节数 `< 300 KiB`：判定为“断流假死”或连通性极差，直接淘汰淘汰（`eliminated_reason: 断流假死`）。
  - 完全无法连通外网且速度为 0：判定为死节点淘汰（`eliminated_reason: 无法连通外网`）。

---

## 6. 打标与规范命名体系 (Canonical Naming)

### 6.1 节点命名结构
```text
[国旗] [❇️] [✨️] [Fast] [国家]_[编号][落地后缀][流媒体后缀][来源后缀]
```

### 6.2 标签位解析
1. **国旗 Emoji**：
   - 根据测试最终确定的国家代码（Google 判定优先，GeoIP 为辅）生成对应的国旗 Emoji（如 `🇺🇸`, `🇯🇵`, `🇭🇰`, `🇸🇬`）。
2. **前置能力徽章（国旗后、国名前）**：
   - **`❇️`**：AI 三大全通（ChatGPT + Claude + Gemini 均通过）。
   - **`✨️`**：综合全通能力徽章（必须同时满足：① AI三大全通；② YouTube 免登实播通过；③ 四站免盾达成）。
   - **`Fast`**：高速节点。
3. **国家中文名称**：标准简体中文名称（如 `美国`, `日本`, `香港`, `新加坡`, `德国` 等）。
4. **序号（`Slot`）**：
   - 若保留原有节点，优先继承原编号；
   - 新加入节点从该国最小未被占用的正整数开始分配（`SlotAllocator`），杜绝重号。
5. **后置专属角色与解锁后缀（编号后）**：
   - 落地链路：
     - **`_USAI`**：美国落地节点且 AI 全通。
     - **`_Lnd`**：常规中转落地节点。
   - 流媒体：
     - **`_NF`**：Netflix 解锁。
     - **`_D+`**：Disney+ 解锁。
   - 来源：
     - **`_ChromeGo`** 等自定义来源标识。

### 6.3 典型命名示例
- `🇺🇸 ❇️✨️美国_1_USAI_NF_D+`：美国落地、AI全通、综合全通（免盾+YT免登）、支持奈飞与迪士尼。
- `🇯🇵 ❇️✨️日本_1_NF`：日本直连前置跳板、AI全通、综合全通、支持奈飞。
- `🇸🇬 ❇️新加坡_2_Lnd`：新加坡落地、AI全通。
- `🇭🇰 香港_3`：香港直连前置跳板。
