# 服务能力测试判据与规范

本文档详述各个测试维度的严格判据、请求端点、特征匹配规则、打标规范及淘汰机制。

---

## 0. 测活与丢包抖动 (Liveness & Packet Loss)

- 轮换 Google / Cloudflare / Apple 204 三端点轻量采样 10 次（`--loss-samples`），记录握手延迟、平均延迟、抖动（`jitter_ms`）与丢包率；起始连续 5 次失败即熔断。
- 丢包率 >= 50%（`--max-loss-rate`）判定不可用并淘汰。
- 丢包率 20%~49%：保留可用，但不可作 Key 前置（`--key-max-loss-rate`），并剥离 ✨️。
- 丢包率 < 20% 才具备 Key/✨️ 资格；需前置的落地按前置丢包率升序、延迟升序择优选前置。

---

## 1. 真实出口与 IP 属地检测 (IP Egress & Geolocation)

### 1.1 双栈出口与基线防污染
- **出口探测端点**：
  - IPv4: `https://api.ipify.org?format=json`, `https://ipv4.icanhazip.com`
  - IPv6: `https://api6.ipify.org?format=json`；Cloudflare trace 返回 IPv6 时也单独归入 IPv6。
- **跑机基线出口（Runner Baseline）**：
  - 跑机基线在后台与测活并行获取：经绑定物理网卡的 mihomo DIRECT 探测；服务首次核对出口时等待基线结果，不把 `probe_egress(None)` 的系统路由出口当作物理直连。
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
- 普通非受限地区的分歧优先取全源有效票严格多数（`majority_vote`）；平票且纯 GeoIP 有共识时以 GeoIP 为准；平票无共识或无其他有效证据时以 Google/Gemini 观测地区兜底（保留候选、来源和 `is_inconsistent=True` 标志）；绝不用原节点国旗或名称兜底。

### 1.3 出口绑定的多源 GeoIP
- 固定 IP 反查：IPinfo、ipwho.is、ipapi.is、DB-IP；全部 HTTPS，每条来源须回显同一有效公网 IP 才能投票。注册地、ASN 国别不作为地理位置。
- ipapi.is 兼容嵌套 `location.country_code` 和无密钥 free-tier 英文 `country` 两种已实测响应。
- 来源族去重：至少两票且严格超过 50% 才形成共识。平票、单来源、错误、字段缺失均不产生确定国别；不按国家黑名单丢弃真实 SC/CY 等记录。
- Cloudflare `loc` 是辅助 GeoIP 观测；`colo` 是 CF 接入机房，不计票、不作“物理锚点”。
- 出口 IPv4/IPv6 分别归档，按 IP 反查；双栈不等于轮换池。同族多 IP、前后变化、跨 IP 国别冲突需要标记。Google 请求只验证其服务地区，不能证明其目的站出口一定等于回显站出口。
- 不复用旧 `google_multi_signals` 为有效来源。默认无跨运行 GeoIP 缓存，HTTP 429/超时/解析错误完整留痕。
- 详细判据、开源参考与纯属地复核命令见 [geolocation.md](geolocation.md)。

### 1.4 IP 信誉与家宽综合判定体系 (Composite Reputation & Residential Engine v3.0)
彻底打破对单一第三方 API 的依赖，构建“本地 PTR/ASN + 24小时持久化 SQLite 缓存 + Scamalytics/DNSBL 权威反欺诈 + Net.Coffee 兜底容灾”的渐进式多维综合评估架构。

- **三层极速探测流水线**：
  1. **本地极速层 (0-20ms)**：本地 SQLite 24小时有效缓存（命中直接返回）；本地 `socket.gethostbyaddr` rDNS/PTR 域名特征提取；核心 Eyeball/IDC ASN 分类；
  2. **基础元数据层 (100-250ms)**：IPinfo、ipwho.is 基础属性与 DoH/DNSBL 黑名单快速检测；
  3. **权威风控与兜底层 (200-400ms)**：Scamalytics 免 Key 欺诈分与代理标记结构化提取；AbuseIPDB 恶意威胁（免配置自动短路，有 Key 自动富化）；Net.Coffee 仅作为后备兜底。
- **家宽真实性四级形态精确分类（严禁采信上游节点自标名称）**：
  - **硬性准则**：`🏠` 与 `_ISP` 必须依赖真实网络层探测（ASN 归属、ISP 组织名、rDNS/PTR 反向域名正则、Scamalytics 欺诈与机房/代理标记、多源 GeoIP flags），**严禁因为上游节点原名自标“家宽 / 双ISP / 住宅 / residential / HiNet”就直接授予 `🏠` 或 `_ISP`**，上游残留的自标家宽字样一律清洗剔除。
  - **Level 1: 原生民用住宅宽带 (True Residential)**：ASN 属于已知 Eyeball 运营商且（PTR 命中动态住宅正则，或确认为非机房且无机房 PTR）。**若信誉分 >= 80 且无任何 cf-mitigated 硬拦截、无污染标记授予 `🏠` 专属徽章；若 < 80 授予 `_ISP` 后缀**。
  - **Level 2: 商用/机房双 ISP (Commercial Dual-ISP)**：真实网络层检测属于 ISP 机构或具备双 ISP/住宅属性，但位于 IDC 托管环境或缺乏民用动态 PTR。**严禁授予 `🏠` 徽章，统一授予纯英文 `_ISP` 后缀**。
  - **Level 3: 住宅代理池 (Residential Proxy)**：高危轮换池或黑灰产代理。**剥离 `🏠` 与 `♥️` 资格**，列入风控警告池。
  - **Level 4: 数据中心/机房 (Datacenter / Hosting)**：纯机房/云商节点，不带家宽相关标记。
- **综合信誉评分计算模型 (Composite Reputation Score: 0–100)**：
  $$\text{Score} = \text{Base}(100) - \text{Penalty}_{\text{Fraud}} - \text{Penalty}_{\text{Abuse}} - \text{Penalty}_{\text{DC}} - \text{Penalty}_{\text{Blacklist}} + \text{Bonus}_{\text{CleanRes}}$$
  - 欺诈扣分：Scamalytics 分数 <= 15 扣 0 分；16-40 扣 `(Score-15)*0.5` 分；>40 扣 `25 + (Score-40)*0.8` 分；
  - 恶意扣分：AbuseIPDB 滥用分 * 0.4；
  - 机房扣分：纯机房固定扣 10 分（基准上限 90）；
  - 黑名单扣分：DNSBL 命中每项扣 15 分；
  - 纯净家宽奖励：Level 1 且欺诈分 < 10 奖励 +5 分（上限 100 封顶）。

---

## 2. AI 平台解锁检测 (AI Unlock)

六大主流顶级 AI 平台独立检验，所有接口要求目标服务本身返回“地区允许”或“鉴权穿透”证据，杜绝因凭据失效或网络错误导致的误判。并发线程池探测保证单节点检测耗时控制在 1.5~2.5 秒内。

| 平台 | 探测端点 | 判定依据 (`passed`) | 失败/封锁判定 (`blocked`) |
|---|---|---|---|
| **ChatGPT (OpenAI)** | 1. 合规接口：`https://api.openai.com/compliance/cookie_requirements`<br>2. 状态接口：`https://ios.chat.openai.com/public-api/mobile/server_status/v1` (UA: `ChatGPT/1.2024.000`)<br>3. 模型接口：`https://api.openai.com/v1/models` | 合规接口返回 `200` 且正文含 `cookie_consent_required` 证明地区允许；且状态接口返回 `200` 或模型接口返回 `401`（未授权证明连通）即判定解锁。 | 合规接口返回 `403 unsupported_country_region_territory` 为地区封锁。 |
| **Claude (Anthropic)** | 模型端点：`https://api.anthropic.com/v1/models` | 返回 `401`（Unauthorized）或 `200` 即判定解锁（证明成功到达模型网关）。 | 返回 `403` 且正文含 `Request not allowed` 判定为地区封锁。 |
| **Gemini (Google)** | 页面端点：`https://gemini.google.com/` | 正文解析到标志 `[45631641,null,true]` 且地区非大陆（非 `CN`/`CHN`）。 | 正文含可用性标志为 `false`、正文包含 `not supported in your country` 或地区码为 `CN`。 |
| **Groq** *(新增)* | 1. `https://console.groq.com/`<br>2. `https://chat.groq.com/`<br>3. `https://api.groq.com/openai/v1/models` | Console 与 Chat 均返回 `200` 且无阻断正文；模型接口返回 `401`（未授权提示 `invalid_api_key`）或 `200`。 | 任一端点返回 `403` 且正文含 `Access denied. Please check your network settings.`，或遭遇 Cloudflare 质询盾。 |
| **Hugging Face** *(新增)* | 1. `https://huggingface.co/`<br>2. `https://huggingface.co/api/models?limit=1` | 首页返回 `200` 且含 `huggingface` 特征；且轻量 API 返回 `200` 并成功解析模型数据 JSON。 | 状态码 `403`、`1020`、出现 Cloudflare 质询拦截特征或 GFW SNI 重置。 |
| **Grok (xAI)** *(新增)* | 1. `https://grok.com/`<br>2. `https://api.x.ai/v1/models` | `grok.com` 返回 `200` 且正文含 `cdn.grok.com` 或 `grok` 标志；无 CF 质询头；模型接口返回 `401`（未授权提示 `No credentials presented`）或 `200`。 | 超时（GFW 阻断）、返回 `403`/`451`、或响应含 `cf-mitigated: challenge` / `Just a moment` / `not available in your region`。 |

- **AI 服务全解锁条件 (`❇️` 徽章)**：
  出口稳定 + 真实出口非送中 + ChatGPT 通过 + Claude 通过 + Gemini 通过 + Hugging Face 通过 + Grok 通过（剔除 Groq，5 项全通即授予 `❇️`）。
- **综合全通能力徽章 (`✨️` 徽章)**：
  必须同时满足：**AI 五大核心全通 + 成功解锁 Groq + YouTube 免登实播通过 + 五站免盾通过（WAF Shield Score >= 85 且至少 4 站完美直通） + 丢包率 < 20%**。只有解锁 Groq 才能给 `✨️`！

---

## 3. YouTube 免登录实播检测 (Anonymous YouTube Playback)

非普通 API 连通性测试，而是验证无 Cookie、无登录状态下的真实媒体流播放与抗机器人风控能力。

- **浏览器环境**：Playwright 驱动完整版 Chromium（`channel="chromium"`），关闭自动化特征（`--disable-blink-features=AutomationControlled`，`--disable-quic`，locale: `en-US`）。
- **测试样本视频**：`jNQXAC9IVRw`, `YE7VzlLtp-4`, `M7lc1UVf-VE`。
- **HTML5 播放观察者（Playback Observer）**：
  - 动态监听 `<video>` 元素的播放事件与时间戳更新。
  - **达标条件**：健康播放累计 `>= 10.0` 秒，结束时非停滞且 `readyState >= 3`；进度变化须与墙钟一致，跳进度、缓冲、广告不计时。
  - **风控与限制判定**：
    - `bot_required`：页面提示 "Sign in to confirm you’re not a bot" 或出现 Turnstile/Captcha 人机验证。
    - `sign_in_required`：需要登录才能观看。
    - `rate_limited`：429 或流量限制。
    - `playback_start_failed`：无法起播。
- **双向出口复核（Double Egress Check）**：
  - 播放前：浏览器 Context 访问出口检测接口，确认当前浏览器 IP 确实等于被测节点 IP。
  - 播放后：再次核对浏览器出口 IP，前后任一缺失、变化或与节点 IP 不符都判 `browser_egress_unverified`；不从 HTML 错误页中抽取 IP。回显站失败时尝试独立 HTTPS 端点，并记录 `youtube_details.egress`。
- **通过标准**：至少成功实播通过 **2 个** 独立样本视频。

---

## 4. 异构 5 站免盾与防降智探测体系 (WAF Shield & Anti-Degradation Probe v3.0)

全面替代传统简单的单站 HTTP 状态码与文本匹配，消除探测脚本自身 TLS 指纹暴露造成的“假弹盾”，并深度量化识别 HTTP 200 下的 AI 算力惩罚与隐性降智。

- **自适应双模 TLS 指纹通信底座**：
  - **Mode A (增强仿真模式)**：存在 `curl_cffi` 时，启用 1:1 Chrome 131 BoringSSL JA4 扩展乱序与 HTTP/2 握手仿真；
  - **Mode B (零依赖回退模式)**：未安装时，自动调用深度调优的 `ssl.SSLContext`（Chrome 加密套件排序 + ALPN 强制协商 + 完整 Client Hints 伪装）。
- **两阶段流式截断探测 (Two-Stage Streaming)**：
  - **阶段一**：响应头毫秒级短路判定（0 KB Body 下载），命中 `cf-mitigated: challenge` 或 Google `/sorry/` 立即关闭流；
  - **阶段二**：流式截断下载（最多仅读前 16KB），单节点 5 站并发总耗时控制在 350ms–550ms。
- **异构五站探针矩阵与四级灰度赋分 (满分 100 分，每站 20 分)**：
  1. **OpenAI Sentinel (AI 算力盾)**：POST `https://chatgpt.com/backend-api/sentinel/chat-requirements`，解析 `proofofwork.difficulty` 十六进制阈值（`>= 0x0ffff` 满血 20分，`0x00010 <= diff < 0x0ffff` 12分，`< 0x00010` 坐实降智惩罚 6分，拦截 0分）；
  2. **Google & YouTube (reCAPTCHA Enterprise)**：Google 搜索 429//sorry/ 拦截 + YouTube 登录/机器人墙（`Sign in to confirm you’re not a bot`）扫描；
  3. **Reddit Fastly (严苛机房 ASN 盾)**：`/r/all/top.json` 数据直通 (20分) vs 403 `Blocked by network security` 硬拦截 (0分)；
  4. **TikTok / X Social (商业社媒反爬)**：会话建立直通 (20分) vs 滑块验证码 `verify-bar` / `captcha` (6分)；
  5. **Cloudflare Strict & Trace (CF 官方挑战头与套壳核验)**：严格站无 `cf-mitigated` 挑战 (15分) + `1.1.1.1/cdn-cgi/trace` 原生出口 `warp=off` (5分)；检测到 `warp=on/plus` 扣 8 分并标记套壳。
- **免盾综合得分 (WAF Shield Score 0–100) 与徽章授权**：
  - **`[✨️]` 综合全通徽章**：必须满足 **WAF Shield Score >= 85** 且至少 4 站完美直通 + AI 全通 + Groq 解锁 + YouTube 免登实播 + 丢包率 < 20%；
  - **`[❇️]` AI 服务徽章**：AI 五平台全通 + OpenAI Sentinel **无高危降智惩罚**（未判定为 `DEGRADED_HEAVY`）；
  - **`[⚡WARP]` 污染标记**：实测 `warp=on` 或 `warp=plus` 时自动追加 `[⚡WARP]` 套壳标记，剥夺 `🏠` / `♥️` / `✨️` 及 `_ISP`，但**保留 AI 解锁标记（`❇️` / `_USAI` / `_GOAI`）**。

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
- **执行时机**：两种内核共用双线调度。直连节点一判活即入服务线与测速线，不等整批；本地测速严格串行（`--speed-concurrency 1`），云端默认 2 路。任务互斥保护节点及其前置，受并行检测干扰且未达标时延后到服务线结束再测。落地测速等待直连前置最终带宽及出口证据（含空闲重测），不把“前置还没测完”误作“没有前置”。
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
- **拓扑、家宽与出口硬门槛**：
  - 必须是直连节点，落地节点绝对禁止充当 Key；
  - **真家宽节点（`🏠`）专作高纯净度终端出口，一律排除在 Key 前置跳板候选之外**（避免大流量中转消耗珍贵住宅带宽或触发家宽风控）；
  - 节点出口 IP 真实有效，严禁与本地跑机基线出口重合。
- **测速硬门槛**：
  - 必须通过上述 5.3 节的持续下载测速（`verdict=qualified`：稳态 >= 12 Mbps 且最低 >= 6 Mbps）。
- **丢包与稳定性硬门槛**：
  - 测活丢包率必须健康（`loss_rate < 20%`，超出阈值严禁充当 Key 前置跳板）。
- **加权评分模型（满分 48 分，实现见 `scripts/core/key_evaluator.py`）与配额**：
  - **协议分类分（满分 10 分）**：`tls-tcp`（`vless`/`trojan`/`vmess`+TLS/Reality/WS/gRPC，10分） > `self-enc`（`ss`/`ssr`/`vmess` 无 TLS，6分） > `cdn-plain`（明文 `ws`/`grpc`，4分） > `udp`（`hysteria2`/`hysteria`/`tuic`/`wireguard`，3分）；
  - **亚太核心区加分（满分 8 分）**：香港（HK）、台湾（TW）、日本（JP）、新加坡（SG）、韩国（KR）加 8 分；
  - **速度得分（满分 15 分）**：按 `min(15.0, (speed_mbps / 50.0) * 15.0)` 线性折算；
  - **延迟得分（满分 10 分）**：`<= 50ms` 满分 10 分，线性递减至 `550ms` 为 0 分；
  - **低丢包稳定性加分（满分 5 分）**：0% 丢包满分 5 分，平滑递减至 20% 丢包 0 分；
  - 综合评分前 N 名授予 `is_key = True`（美国 `_USAI` 节点显示为 `Free` 前缀），并施加单国家配额（默认每国最多 3 个）。

### 5.5 直连 / 需前置节点区分与落地测试（两条流水线一致）
- **首轮测活**：全部节点直连并发探测，每节点轮换 Google/Cloudflare/Apple 204 三端点采样 10 次（前 5 次连续失败即熔断，丢包率 >= 50% 判死淘汰）；原 `dialer-proxy` / `detour` 在临时直连监听中剥离。声明的落地角色仍保留。
- **第二轮**：首轮直连不通的节点以并发 4 直连复测，同时在本地经最多 3 个不同服务器的已判活前置探测。前置须具备协议资格、非落地，按延迟择优；UDP 节点优先用支持 UDP 的前置。云端或 `--no-landing-probe` 不做链式探测。
- **即时服务检测**：任一前置测通即能放行声明落地节点；未声明者优先等待直连复测结论。经前置成功的节点设置 `path=front`、`is_landing=True`，立即执行完整服务；该前置拿不到公网出口时换剩余备用前置，最多合计 3 个。实际前置写入 `front_node`，回退写入 `front_attempts`。
- **落地下载测速**：等待直连测速（含空闲重测）与出口证据，按 Key 候选档 → 备用档（稳态 >= 6 Mbps、最低 >= 3 Mbps）评分选最多 3 个不同服务器前置；经某前置没有样本时换下一个，成功前置写入 `speed_front_node`。没有合格前置则明确记为跳过，不能伪称已测速。
- **统一核对**：服务、测速结束后核验出口与本机/服务前置是否重合，再淘汰并评 Key。实测落地即使原名无 `_Lnd` 也绝不能成为 Key。经最终入选 Key 的前置测得低速按同一门槛淘汰；经非 Key 前置时只记录链路速度，不将前置瓶颈归咎于落地。
- **可用成品约束**：最终前置池必须包含至少一个本轮已验证能承载该落地的保留前置；唯一前置被淘汰时，不能改用未经验证的 HTTP 或 DIRECT 后照常导出落地。无 Key 时保留的备用前置写入默认前置池。
- **未开启测速**：仍可用已判活、具备协议资格的前置做链式测活与服务检测，但不授予 Key/Fast。两入口都不再使用本机客户端端口作为隐藏兜底。
- **报告与失败**：报告保留测试维度、并发参数、逐节点服务/测速完成状态及 AI、YouTube、免盾证据；全部淘汰时仍写报告、返回非零、不导出空配置。

---

## 6. 打标与规范命名体系 (Canonical Naming)

> 编号保留、`--resort` 排序、落地沉底例外与合流规则见 [naming-and-sorting.md](naming-and-sorting.md)。

### 6.1 节点命名结构
```text
[国旗] [✨️] [🏠 / ♥️] [❇️] [Key / Free / Fast] [国家][_城市]_[编号][_IPLC 或 _ISP][落地后缀][流媒体后缀][来源后缀][污染标记]
```

### 6.2 标签位解析
1. **国旗 Emoji**：根据 `geo_decision.cc` 生成。送中节点保留已确认的实际属地并附 `_⚠️CN`；普通强分歧/证据不足用 `🏳️ 未知`，不拿原名当检测结论。
2. **前置能力徽章（国旗后、国名前，严格有序: ✨️ > 🏠 / ♥️ > ❇️ > Key > Fast）**：
   - **`✨️`**：综合全通能力徽章（必须同时满足：① AI五大全通 + Groq解锁；② YouTube 免登录实播通过；③ 免盾达成：WAF Shield Score >= 85 且至少 4 站完美直通；④ 测活丢包率 < 20%）。
   - **`❇️`**：AI 五大核心全解锁（OpenAI + Claude + Gemini + HuggingFace + Grok 均通过），且 OpenAI Sentinel 未判定重度降智。
   - **🏠**：优质家宽专属徽章（具备真实家宽/双ISP特征且综合信誉分 >= 80，无任何 cf-mitigated 硬拦截，与 ♥️ 严格互斥；低分家宽剥离 🏠 改用纯英文 _ISP 后缀，专线家宽只保留 _IPLC）。
   - **♥️**：高信誉机房 IP（具备普通机房属性且综合信誉分 >= 80，无任何 cf-mitigated 硬拦截，与 🏠 严格互斥；送中/污染节点不授予）。
   - **`Key` / `Free`**：评选出的优质直连前置跳板节点。**只有具备“USAI”后缀的美国节点才将 Key 前缀改为 Free 前缀，Free 前缀继承美国节点的 Key 前缀的所有权重**（排序顺位、前置跳板入组资格等完全一致），其他符合 Key 标准的美国节点以及非美节点继续正常使用 Key 前缀。
   - **`Fast`**：主动完整测速达到 Key/Fast 级（稳态 >= 12 Mbps 且最低 >= 6 Mbps）但未被选为 Key/Free 的节点（如 HTTP 高速节点、超出国家配额的节点）。
   - *注：`Key`/`Free` 与 `Fast` 严格互斥，优先授予 `Key`/`Free`；3 秒防断流快检、未开启测速或未达标节点不带 Key/Free/Fast 标签。*
3. **国家中文名称**：标准简体中文名称（如 `美国`, `日本`, `香港`, `新加坡`, `德国` 等）。
4. **序号（`Slot`）**：
   - 默认流水线：本技能规范命名（国旗与国家名一致）的原节点，属地未变化时保留原编号，服务结果变化只更新徽章；
   - 新加入节点及属地变化的节点，从该国最小未被占用的正整数开始补位（`SlotAllocator`），杜绝重号；
   - 仅用户主动要求重排序（--resort）时，同地区按 ✨️ > 🏠 > ❇️ > Key > Fast 排好主排序池位置（🏠 和 ISP 节点内部按原顺序排列不沉底，普通机房节点按 _NF > _D+ > 纯净 > ♥️ > 信誉分，普通机房落地沉底）后，再从 1 重新编号。
5. **后置专属角色与解锁后缀（编号后）**：
   - 专线标识（排在所有后缀的第一位）：
     - **`_IPLC`**：测试节点中带有 IPLC 或专线标识时保留，且严格排在所有后置后缀的第一位。
   - 落地链路：
     - **`_USAI`**：统一认定的美国落地或直连且 AI 全通（直连 USAI 节点在主排序池正常排序不沉底；仅实测需前置的落地节点沉底）。
     - **`_GOAI`**：IP 属地判定存在不一致，但由谷歌认定为美国 IP 且具备原 "USAI" 能力（AI 全通）的节点，不论最终多数决归属到哪个地区（如美国、墨西哥等），均给予 `_GOAI` 后缀（替换原 `_USAI`）；属地未统一认定且非谷歌认定的节点或无 AI 能力的节点严禁授予 `_GOAI`。
     - **`_Lnd`**：常规中转落地节点。
   - 流媒体：
     - **`_NF`**：Netflix 解锁。
     - **`_D+`**：Disney+ 解锁。
   - 来源：
     - **`_ChromeGo`** 等自定义来源标识。

### 6.3 典型命名示例
- `🇯🇵 ✨️♥️❇️Key日本_1_NF`：日本优质直连前置跳板、综合全通（免盾+YT免登）、高信誉 IP、AI全通、测速达标、支持奈飞。
- `🇺🇸 ✨️❇️Fast美国_12`：美国高速直连节点（测速达标，非 Key）、综合全通、AI全通。
- `🇺🇸 ✨️❇️美国_1_USAI_NF_D+`：统一认定的美国落地、综合全通、AI全通、支持奈飞与迪士尼。
- `🇺🇸 ✨️❇️美国_2_GOAI_NF_D+`：仅谷歌认定的美国 IP（属地存在分歧，不授予 USAI，授予 GOAI）、综合全通、AI全通、支持奈飞与迪士尼。
- `🇸🇬 ❇️新加坡_2_Lnd`：新加坡落地、AI全通。
- `🇭🇰 香港_3`：香港直连普通节点。
