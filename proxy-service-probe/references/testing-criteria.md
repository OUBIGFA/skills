# 服务能力测试判据与规范

本文档详述各个测试维度的严格判据、请求端点、特征匹配规则、打标规范及淘汰机制。

---

## 1. 真实出口与 IP 属地检测 (IP Egress & Geolocation)

### 1.1 双栈出口与基线防污染
- **出口探测端点**：
  - IPv4: `https://api.ipify.org?format=json`, `https://ipv4.icanhazip.com`
  - IPv6: `https://api6.ipify.org?format=json`；Cloudflare trace 返回 IPv6 时也单独归入 IPv6。
- **跑机基线出口（Runner Baseline）**：
  - 在探测任何节点前，必须先获取本地/跑机自身的直连公网出口 IP（`probe_egress(None)`）。
  - 若被测节点返回的出口 IP 与跑机自身直连出口一致（`runner_ip_match=True`），说明代理穿透失败或流量走直连泄露，判定为无效节点。
  - 基线必须与节点测试走同一路径：经 mihomo DIRECT 监听并绑定同一物理网卡测得（`--direct-proxy` 显式指定时以其为准）。系统路由出口在开启 TUN/系统代理（如 Karing）时等于本机正在使用的节点出口，只记录不作基线，否则该节点会被误判“出口与本机重合”。物理直连基线测不到时不做重合淘汰并给出警告。
- **出口稳定性（Stability）**：
  - 各项服务探测前后分别采集出口 IP。若前后出口 IP 不一致，标记为出口不稳定（漂移）。

### 1.2 Google 自身地区码与 IP 属地分开记录
- Gemini 的有效 ISO alpha-3 标记优先；YouTube 必须有唯一且一致的 `INNERTUBE_CONTEXT_GL` 和 `countryCode` 才能兜底。缺标记、HTTP 错误、模糊页面不能补成美国；不再以 `google.com` 域名或界面语言定国。
- Google 结果与第三方强共识冲突、与 YouTube 不一致或缺失时，额外复查一次；前后地区变化撤销 Google 定国资格并保留待复核标志。
- 报告分别保留 `google_region`、`ip_info_by_ip`、`geo_decision`；Google 的服务归属不等于物理机房位置。
- **送中/受限地区污染优先按已有专门方案处理**：
  - 例如 IP 属地有韩国共识、Google/Gemini 为 `CN/CHN`：保留韩国，记录 `is_sent_to_china=True` / `is_poisoned=True`，命名后缀 `_⚠️CN`，剥离 AI 全通和综合全通徽章。
  - 不把这类节点改成中国或普通“未知”；是否淘汰仍由任务策略决定，本次属地抽查不修改订阅。
  - 任一次可信 CN 观测不能被后续非 CN 信号投票抹掉。
- 普通非受限地区的强分歧暂定 `UNK`，保留候选、来源和待复核标志，不用原国旗兜底。

### 1.3 出口绑定的多源 GeoIP
- 固定 IP 反查：IPinfo、ipwho.is、ipapi.is、DB-IP；全部 HTTPS，每条来源须回显同一有效公网 IP 才能投票。注册地、ASN 国别不作为地理位置。
- ipapi.is 兼容嵌套 `location.country_code` 和无密钥 free-tier 英文 `country` 两种已实测响应。
- 来源族去重：至少两票且严格超过 50% 才形成共识。平票、单来源、错误、字段缺失均不产生确定国别；不按国家黑名单丢弃真实 SC/CY 等记录。
- Cloudflare `loc` 是辅助 GeoIP 观测；`colo` 是 CF 接入机房，不计票、不作“物理锚点”。
- 出口 IPv4/IPv6 分别归档，按 IP 反查；双栈不等于轮换池。同族多 IP、前后变化、跨 IP 国别冲突需要标记。Google 请求只验证其服务地区，不能证明其目的站出口一定等于回显站出口。
- 不复用旧 `google_multi_signals` 为有效来源。默认无跨运行 GeoIP 缓存，HTTP 429/超时/解析错误完整留痕。
- 详细判据、开源参考与纯属地复核命令见 [geolocation.md](geolocation.md)。

### 1.4 IP 信誉与欺诈风险评估 (Net.Coffee)
该来源不再参与属地投票；须回显被查询 IP 才使用信誉字段，失败保留诊断而不是默认为好 IP。
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
  4 站中**至少 2 站**直接通过（`passed`）或质询自动解除（`auto_passed`）即判定为“规定网站免盾”；未观测（`unknown`）、阻断（`blocked`）与质询未解除（`challenge`）的站点不计入通过数。有浏览器观测的站点以浏览器结果为准，否则以 HTTP 结果为准。

---

## 5. 国际流媒体与带宽防断流检测

### 5.1 国际流媒体
- **Netflix (奈飞)**：
  - 请求非自制剧页面 `https://www.netflix.com/title/81280792` 或 `https://www.netflix.com/title/80018499`。
  - 状态码返回 `200` 判定为解锁；返回 403/404/重定向登录判定为仅解锁自制剧或未解锁。
- **Disney+ (迪士尼)**：
  - 请求 `https://www.disneyplus.com/`。
  - 状态码返回 `200`, `301`, `302` 且页面正文不含 `not available` 或 `unsupported` 判定为解锁。

### 5.2 默认 3 秒流式下载带宽与断流淘汰 (Stall Check)
- **非主动模式默认行为**：
  - 测速目标：`https://speed.cloudflare.com/__down?bytes=10000000` 或 Google DMG。
  - 测速窗：固定 3.0 秒流式下载。
  - 断流淘汰标准：累计传输字节数 `< 16 KiB` 判定为“断流假死”淘汰；完全无法连接且速度为 0 判定为死节点淘汰。

### 5.3 持续下载测速规范 (按真实 YouTube 播放校准，主动要求时启用)
- **触发条件**：仅在用户显式要求测速或传入 `--speed-test` 时激活；本地与 GitHub Actions 同一套判据。
- **执行时机**：每批节点的服务测试（含浏览器实播）全部结束、仍在该批临时监听存活期间，独立进入测速阶段；本地严格串行（`--speed-concurrency 1`），云端 2 路并发。
- **测速目标**（`--speed-target` 可指定单一 URL 覆盖）：
  1. `https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg`（约 280MB，Google 边缘 CDN，与 YouTube 同网络）；
  2. `https://speed.cloudflare.com/__down?bytes=50000000`（仅当 Google 目标连不上或返回非二进制载荷时回退）。
  - 目标为 CDN 域名并经代理由节点侧解析，自动命中离节点出口最近的边缘，不需要按属地配置测速矩阵。
  - 一旦目标已开始返回载荷，就以该目标的结果定论，不因速度低而换目标重测（杜绝挑目标凑高速）。
- **测量方式**：单 TCP 连接、`Accept-Encoding: identity`，拒绝 HTML（劫持页/门户页）与压缩载荷；字节只在内存累计，按 1 秒切片记录速率与 `ttfb_ms`。不使用多连接分片：YouTube 播放器按顺序拉分段，节点常按单连接限速，多连接聚合会得出播放时达不到的"假高速"。
- **为何观测 10~20 秒**：实测用户可流畅播放 4K 的节点（YouTube 连接速度先约 5 Mbps、后稳定 15 Mbps+），新建连接逐秒速率为 1.3、2.5、2.5、3.8、5.0、2.1、7.0、8.8 … 15~19 Mbps，第 10~20 秒才到稳态；旧的"2 秒预热 + 6 秒、每秒达标"会在第 3 秒误判淘汰。
- **稳态指标**（最后 6 秒窗口）：
  - `stable_mbps` 稳态速度：窗口平均；单秒速率按窗口中位数的 2 倍封顶，孤立尖峰不能拉高结论；
  - `floor_mbps` 最低速度：窗口内 2 秒滑动平均的最小值，容忍 1 秒抖动（播放器有缓冲），抓连续下滑；
  - 另报告 `peak_mbps`、`mean_mbps`、`sample_mbps`、`observed_seconds`、`max_stall_seconds`。
- **结论 (`verdict`) 与何时停止**：
  - `qualified`（Key/Fast 级）：`stable >= 12`（`--min-speed-mbps`）且 `floor >= 6`（`--min-floor-mbps`）。观测满 10 秒即可结束，但窗口后半段均值低于前半段 75%（正在下滑、慢慢限速型假高速）时继续观测，由下滑后的稳态决定；
  - `drop`（**淘汰并从输出配置删除**）：`stable < 6`（`--drop-below-mbps`，0 为不按速度淘汰）。观测满 10 秒、最近 3 秒均值 < 4.5 Mbps 且未见爬升时提前结束；贴近淘汰线或仍在爬升的节点观测到 20 秒再定；
  - `keep`：介于两者之间，保留但不授 Key/Fast；
  - 中途断流、超时（`status` 非 `complete`）：不授 Key/Fast，按已测秒数判 `keep` 或 `drop`；完全没有样本判 `drop`。
- **贴近门槛重测**：结论为 `drop` 但稳态 >= 3.6 Mbps（淘汰线 60%）、为 `keep` 但稳态 >= 9.6 Mbps（Key 门槛 80%），或没有样本时，用新连接完整重测一次，取较好结论；两次摘要记录在 `attempts`。同一节点实测单次稳态可在 6~23 Mbps 间波动，重测减少偶发误删。
- **先突发后限速的防护**：开头突发的秒数不在稳态窗口内；突发延伸进窗口的单秒被 2 倍中位数封顶；限速后的连续低速拉低 `floor`；逐步限速被"下滑不提前判达标"拦下。
- **带宽上限**（`--rate-limit-mbps`）：默认 local 40 / ci 50 Mbps，必须不低于 Key 门槛且不超过 100。稳态窗口每 2 秒都接近上限时报告 `capped=true`，表示真实能力不低于上限。
- **观测位置**：本地测的是"本机网络 → 节点 → CDN"，云端测的是"云端机房 → 节点 → CDN"，后者不包含国内网络到节点这一段。报告 `speed_profile.vantage` 注明来源，两者结论不混用。本地运行时若没有节点达标，会提示检查本机宽带是否低于带宽上限。

### 5.4 Key 优质前置跳板节点判定标准 (Key Qualification)
Key 节点是专门用于在落地节点（`_Lnd`/`_USAI`）建立多跳链路时的第一跳（Jump Host），其质量直接决定后续所有落地节点的连通率与稳定性。
- **协议准入硬门槛**：
  - **严禁**：`http`、`https`、`socks`、`socks5` 充当 Key（无加密易被干扰，且 CONNECT 无法中转非标端口落地）。
  - **支持**：`ss`、`vmess`（含TLS）、`vless`（含TLS/Reality/ws/grpc）、`trojan`、`hysteria2`、`tuic`。
- **拓扑与出口硬门槛**：
  - 必须是直连节点，落地节点绝对禁止充当 Key；
  - 节点出口 IP 真实有效，严禁与本地跑机基线出口重合。
- **测速硬门槛**：
  - 必须通过上述 5.3 节的持续下载测速（`verdict=qualified`：稳态 >= 12 Mbps 且最低 >= 6 Mbps）。
- **加权评分与配额**：
  - 协议分类分：TLS-TCP (10分) > Self-enc (6分) > CDN-plain (4分) > UDP (3分)；
  - 亚太核心区加分：香港（HK）、台湾（TW）、日本（JP）、新加坡（SG）、韩国（KR）优先加分；
  - 综合评分前 N 名授予 `is_key = True`，并施加单国家配额（默认每国最多 3 个）。

### 5.5 直连 / 需前置节点区分与落地测试 (`probe_services.py` 测速模式)
- **第一轮直连**：所有节点直连测试（节点自带的 `dialer-proxy` 在测试监听中剥离）。直连可通的节点为直连路径；原名声明为落地（`_Lnd`/`_USAI`/`dialer-proxy`）的仍保持落地角色。
- **需前置候选**：直连拿不到公网出口的节点（`direct_unreachable`）。出口与本机重合、断流等其他淘汰原因不参与重测。
- **前置选择**（第一轮全部完成、Key 评选之后）：
  1. 有 Key：用评分最高的 Key；
  2. 无 Key：从具备前置资格（非 HTTP/SOCKS、非落地、出口有效）且测速未被淘汰（稳态 >= 6 Mbps、最低 >= 3 Mbps，约 1080p 流畅）的直连节点中，按 Key 同一评分规则取最高者；前 10 名标记为备用前置；
  3. 两者都没有：不重测，淘汰原因写明"无合格前置可用于验证"。
- **落地节点的速度淘汰**：经 Key 前置测得的链路速度代表落地节点能力，稳态 < 6 Mbps 同样删除；经备用前置或本机客户端端口时链路受前置限制，只记录测速、不按速度删除。
- **经前置重测**：候选节点以前置为 `dialer-proxy` 链式测试，执行与直连节点相同的全部服务测试和测速（测速反映整条链路）。出口必须不同于本机出口与前置自身出口，否则判为"流量未经该节点转发"淘汰。通过者 `is_landing=True`、`path=front`，报告记录 `front_node`，命名加 `_Lnd`/`_USAI`，配置中注入 `dialer-proxy: 🛡️ Front前置`。
- **未开启测速**：没有带宽证据就无法选前置，只提示直连不可达节点可能需要前置。
- **sing-box 备用流水线**：`probe_singbox.py` 采用同一规则（sing-box 以节点出站作 `detour` 前置），前置优先级为 Key → 备用前置 → `--front-proxy` 本机客户端端口（默认 127.0.0.1:3067，未监听即跳过，未开启测速时唯一可用的前置）。落地节点的浏览器实测沿用同一前置；无可用前置时落地节点跳过浏览器实测。直连初筛整批兜底上限为 120 秒（属地多源复核经慢链路可达 20 秒左右）。

---

## 6. 打标与规范命名体系 (Canonical Naming)

### 6.1 节点命名结构
```text
[国旗] [✨️] [❇️] [♥️] [Key / Fast] [国家][_城市]_[编号][落地后缀][流媒体后缀][来源后缀]
```

### 6.2 标签位解析
1. **国旗 Emoji**：根据 `geo_decision.cc` 生成。送中节点保留已确认的实际属地并附 `_⚠️CN`；普通强分歧/证据不足用 `🏳️ 未知`，不拿原名当检测结论。
2. **前置能力徽章（国旗后、国名前，严格有序）**：
   - **`✨️`**：综合全通能力徽章（必须同时满足：① AI三大全通；② YouTube 免登实播通过；③ 四站免盾达成）。
   - **`❇️`**：AI 三大全通（ChatGPT + Claude + Gemini 均通过）。
   - **`♥️`**：高信誉 IP（Net.Coffee 信誉分 >= 80，出口稳定且全部出口有绑定证据；送中/污染节点不授予）。
   - **`Key`**：评选出的优质直连前置跳板节点。
   - **`Fast`**：主动完整测速达到 Key/Fast 级（稳态 >= 12 Mbps 且最低 >= 6 Mbps）但未被选为 Key 的节点（如 HTTP 高速节点、超出国家配额的节点）。
   - *注：`Key` 与 `Fast` 严格互斥，优先授予 `Key`；3 秒防断流快检、未开启测速或未达标节点不带 Key/Fast 标签。*
3. **国家中文名称**：标准简体中文名称（如 `美国`, `日本`, `香港`, `新加坡`, `德国` 等）。
4. **序号（`Slot`）**：
   - 默认流水线：本技能规范命名（国旗与国家名一致）的原节点，属地未变化时保留原编号，服务结果变化只更新徽章；
   - 新加入节点及属地变化的节点，从该国最小未被占用的正整数开始补位（`SlotAllocator`），杜绝重号；
   - 仅用户主动要求重排序（`--resort`）时，同地区按 `✨️ > ❇️ > Key > Fast > _NF > _D+` 排好全部位置（`♥️` 与信誉只在标签相同的节点之间排位，落地沉底）后，再从 1 重新编号。
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
- `🇯🇵 ✨️❇️♥️Key日本_1_NF`：日本优质直连前置跳板、综合全通（免盾+YT免登）、AI全通、高信誉 IP、测速达标、支持奈飞。
- `🇺🇸 ✨️❇️Fast美国_12`：美国高速直连节点（测速达标，非 Key）、综合全通、AI全通。
- `🇺🇸 ✨️❇️美国_1_USAI_NF_D+`：美国落地、综合全通、AI全通、支持奈飞与迪士尼。
- `🇸🇬 ❇️新加坡_2_Lnd`：新加坡落地、AI全通。
- `🇭🇰 香港_3`：香港直连普通节点。
