---
name: proxy-service-probe
description: 对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登实播、免盾过盾、流媒体、打标命名、本地测速与Key节点筛选及Clash/Mihomo配置渲染，以及用户主动触发时的FoFa/Quake空间测绘订阅搜索与节点提取）时使用。
---

# 代理节点服务能力测试与配置渲染 (proxy-service-probe)

对代理节点（Clash YAML、sing-box JSON、节点订阅链接或 URI）执行全方位的服务能力检测、智能淘汰断流与失效节点、生成规范化角色与能力标签，并依据项目级 `template.yaml` 渲染导出完整的 Clash/Mihomo 订阅配置文件。

**流水线选择**：`probe_services.py`（mihomo 内核）为**主流水线**，默认一律使用，支持全部输入格式、本地/GitHub Actions Profile 与云端运行。`probe_singbox.py`（sing-box 内核）为**备用流水线**，仅在用户明确要求用 sing-box 内核验证兼容性、或需要直接产出 sing-box JSON 时使用。两者共用 `core.probe_flow`：并发测活 → 服务检测线（默认并发 4）∥ 下载测速线（本地串行）→ 统一交叉核对与导出；节点一判活就入队，不等整批完成。测速线仅在主动开启测速时运行。

## 核心契约

> [!IMPORTANT]
> **默认行为准则**：
> 1. **全量服务检测**：本技能默认执行涵盖 IP 属地、AI 三大平台解锁、Playwright Chromium YouTube 免登录实播、4 站免盾检测与国际流媒体解锁。严禁擅自启用轻量模式；`--no-browser` 仅作为用户显式指定或系统无浏览器环境时的降级保底选项。
> 2. **测速非主动技能契约**：**节点持续下载测速为非主动技能**。默认流水线仅执行 3 秒轻量防断流快检（<16KB 淘汰）；**仅当用户明确主动要求**（如指令中包含“测速”、“测试节点速度”、“测速筛选”或显式传入 `--speed-test`）时，才启动完整持续下载测速流水线并执行 Key 节点遴选与打标。本地与 GitHub Actions 使用同一套代码与判据，`--profile auto` 按环境自动选择资源参数；两处各自独立完整运行，不做云端粗筛 + 本地精测的拆分协同。
> 3. **编号稳定契约**：流水线默认保留原节点编号（属地未变即不改号），新节点按国家补空号；**仅当用户明确要求重排序/重编号**时才传 `--resort`，且重排序必定先定位置再从 1 重新编号。
> 4. **空间测绘订阅搜索主动契约 (FoFa / 360 Quake)**：**空间测绘搜索与订阅抓取为非主动触发能力**。默认流水线绝不主动发起网络资产扫描；**仅当用户明确主动要求搜索订阅**（如指令中包含“搜索订阅”、“FoFa 搜索订阅”、“Quake 搜索订阅”或显式调用 `fofa_search.py` / 传入 `--input fofa:...` / `--input quake:...` / `--input spatial:...`）时才启动。FoFa Token/Key 与 Quake Key 以独立变量形式在技能主目录下的 [fofa_config.json](fofa_config.json) 中进行统一配置与引用；默认单页拉取 80 条目标资产；双引擎具备高容错独立性，单一引擎故障不阻断另一个，搜索到的目标订阅地址自动执行规范化全局去重；**单订阅源节点数 > 200 自动过滤丢弃**，以杜绝公开低质聚合源与大量重复死节点浪费测试时间。详见 [fofa-subscription-search.md](references/fofa-subscription-search.md)。
> 5. **合流并入与编号排序契约**：每次拉取完订阅并经去重、全量测活测速与服务检测后，若要并入其他目标订阅配置（Clash YAML / sing-box JSON），**默认根据规则重新排序和编号，优先保留目标订阅的原节点以及原有编号**，新节点按国家在空缺/后续分配空号补齐（并按标准地区聚拢排序）；**仅当用户明确要求中间插入（`--insert` 或 `--resort`）时**，才打破原有编号壁垒，完全按能力顺位（`✨️ > ❇️ > Key > Fast > _NF > _D+ > ♥️`）重排序并从 1 重新依次递增连续编号。详见 [local-operations.md](references/local-operations.md)。

1. **测试范围与判定依据**：
   - **IP 属地与出口**：HTTPS 双栈出口及前后复核；Gemini 显式地区码优先、YouTube 双标记一致才兜底；IPinfo、ipwho.is、ipapi.is、DB-IP 按实际出口绑定交叉验证，Cloudflare `loc` 仅作辅助、`colo` 不参与定国。判定仍为未知的节点最终一律以 Google/Gemini 观测地区为准（Gemini 优先、标待复核），两者都无显式地区才保留未知；送中/受限地区污染沿用实际属地 + `_⚠️CN` 等标记，剥离 AI 全通资格。Net.Coffee 仅保留 IP 绑定成功的信誉信息。详见 [geolocation.md](references/geolocation.md)。
   - **IP信誉与排序**：Net.Coffee `trust_score` 仅作为第三方 0–100 估计，不代表速度或解锁；严格校验 0–100 有限数值。多出口必须全部有绑定信誉证据，节点取已观测出口最低分；出口不稳定或缺证据记为未知。信誉只在用户主动要求重排序（`--resort`）时参与同标签内排位，未知排在有证据节点之后，不跨越地区、落地沉底或 Key/Fast/能力硬规则。
   - **AI 解锁**：涵盖五大核心 AI 平台（OpenAI/ChatGPT 合规与状态端点、Claude 模型端点 401 判通、Gemini 页面可用性标志 `[45631641,null,true]` 实测、Hugging Face 首页与轻量模型 API 双重验证、Grok xAI 首页 200 与模型端点 401 穿透）；五项通过且出口稳定非送中标记为“AI服务全解锁（`❇️`）”；Groq 作为 `✨️` 专属考察指标。
   - **YouTube 免登录实播**：Playwright Chromium 真实无头环境，注入 HTML5 播放观察者（实播 >= 10 秒、非缓冲停滞、非人机验证 / bot_required），播放前后双向复核浏览器出口 IP，通过 2 个视频判定免登实播达标。
   - **过盾 / 免盾**：HTTP 初查 + 浏览器针对 4 站（Cloudflare 官网、ChatGPT、Claude、Gemini）的质询检测，4 站中至少 2 站直接通过或质询自动解除即判定为免盾；未观测（`unknown`）、被阻断或质询未解除的站点不计入通过数。
   - **流媒体与防断流**：Netflix（非自制剧 200）、Disney+ 页面可用性；默认 3 秒流式下载窗口防断流检测，累计传输不足 16KB 判定为断流假死并淘汰。
   - **持续下载测速 (主动触发，按真实 YouTube 播放校准)**：单连接、内存计数不落盘，经节点下载 Google 下载 CDN（与 YouTube 同属 Google 边缘网络，失败前才回退 Cloudflare）。跨境新建连接爬升慢，因此至少观测 10 秒、最多 20 秒，取最后 6 秒为稳态窗口：**稳态速度**（窗口平均，单秒按窗口中位数 2 倍封顶）>= 12 Mbps 且**最低速度**（2 秒滑动平均最小值）>= 6 Mbps 为 Key/Fast 级；**稳态 < 6 Mbps 直接淘汰删除**；介于两者之间保留但不授标。正在下滑的节点不提前判达标，贴近门槛的结论自动重测一次。详见 [testing-criteria.md](references/testing-criteria.md) 5.3 节。

2. **多客户端防破坏与安全隔离方案 (兼容 Karing / Sing-box / Mihomo / Xray)**：
   - **零系统破坏**：严禁碰触 Windows 注册表 IE 代理设置（`ProxyEnable`/`ProxyServer`）及系统路由表。测试流量 100% 局限在本地环回端口。
   - **动态端口避让**：自动避让已知客户端常用端口黑名单（`7890-7895, 9090, 2080-2081, 3067, 10808-10809, 24999`），所有批次严格申请动态空闲端口，杜绝端口冲突导致用户客户端崩溃。
   - **物理网卡绑定防 TUN 劫持**：测试内核关闭 TUN，仅监听回环端口。Windows 自动探测活跃物理网卡，mihomo 的节点出站与 DIRECT 基线绑定同一网卡；系统路由出口只记录、不作淘汰基线。sing-box 在有物理网卡时统一经该网卡的 mihomo DIRECT 中继出网，不依赖出口回显差异来猜测 TUN（回显站点可能被本机客户端分流直连）。中继启动失败即停止，不能悄悄改走 TUN；未能确定网卡时明确不启用中继。
   - **带宽保护与双线隔离**：测速上限不得低于合格门槛（本地默认 40 Mbps、云端 50 Mbps）。服务线与测速线交错并行，但同一节点及其前置不同时被测速与服务任务占用；本地下载测速严格串行。流量统计显示受并行检测干扰且未达标时，等服务线结束后空闲重测。

3. **Key 优质前置跳板遴选与打标体系**：
   - **Key 准入硬门槛**：
     - 严禁 `http`、`https`、`socks`、`socks5` 作为 Key（因无加密或不支持非 443 端口 CONNECT，无法中转非标端口落地节点）；
     - 落地节点（`_Lnd`, `_USAI`）绝不可作为前置跳板；
     - 出口必须真实出网且不与本地跑机基线 IP 重合；
     - 必须通过持续下载测速（稳态 >= 12 Mbps 且最低 >= 6 Mbps）。
   - **Key 优选与配额**：TLS-TCP 强加密加分，亚太核心区（`HK`, `TW`, `JP`, `SG`, `KR`）优先加分，并执行区域配额限制。
   - **直连 / 需前置节点区分（两条流水线一致）**：先并发直连测活；首轮不通的节点低并发直连复测，同时经最多 3 个不同服务器的已判活合格协议前置测活。经前置测通立即进入完整服务检测，服务拿不到公网出口时换备用前置；不要求事先评出 Key。开启测速时，落地测速等待直连前置的带宽与出口证据（含空闲重测），按 Key 候选 → 备用档（稳态 >= 6 Mbps、最低 >= 3 Mbps）最多备 3 个前置，无样本换下一个。汇总才统一淘汰、评 Key；实测落地即使没有原落地标记也绝不作 Key/Front。最终前置池必须保留至少一条已验证的落地链路，否则该落地不导出。未测速时仍做前置测活和服务检测，但不授 Key/Fast；不再使用本机客户端端口兜底。`--no-landing-probe` 关闭前置复测，云端不做前置链式测活。详见 [testing-criteria.md](references/testing-criteria.md) 5.5 节。
   - **打标与规范命名体系**：
     - 前置标识顺序：严格为 `[国旗] [✨️] [❇️] [♥️] [Key / Fast] [国家][_城市]_[编号][落地后缀][流媒体后缀][来源后缀]`。
     - `✨️`：综合全通能力徽章（AI五大全通 + Groq解锁 + YouTube免登录实播通过 + 四站免盾）。
     - `❇️`：AI 五大核心全解锁（OpenAI + Claude + Gemini + HuggingFace + Grok）。
     - `♥️`：高信誉/纯净 IP 徽章（Net.Coffee IP 质量信誉评分 >= 80 分，且出口稳定、所有出口均有绑定证据；带 `_⚠️CN` 等污染标记的节点不授予）。
     - `Key`：评选出的优质前置跳板节点（如 `🇯🇵 ✨️❇️♥️Key日本_1`, `🇺🇸 ❇️Key美国_1_NF`）。
     - `Key` 与 `Fast` 严格互斥；仅主动完整测速达标才授予 Fast/Key，3 秒防断流快检不授予；未开启测速或未达标节点不带 Key/Fast 标签。
   - **编号保留准则（默认流水线）**：
     - 本技能规范命名的原节点，若本轮属地未变化，保留原编号；服务测试结果变化只更新徽章与后缀，编号不变；
     - 新加入节点、属地已变化的节点（视为新节点）按国家从 1 开始补最小空号，不挤占原节点编号；
     - 地区顺序中，中国排在所有已知国家/地区之后（包括未列入常用顺序的地区），未知最后；同地区内直连在前、落地沉底，其余按编号升序，不做能力重排。
   - **重排序与重编号（仅用户主动要求时，`--resort`）**：重排序必定重编号，严格“先定位置、再编号”：
     - 同地区内严格按「直连优选 → 直连普通 → 落地沉底」排列；
     - 直连优选顺位严格遵循：`✨️ > ❇️ > Key > Fast > _NF > _D+`；`♥️` 不跨越这些标签层级，只在标签完全相同的节点之间优先（如同为 `Fast` 时 `♥️` 在前），再按 Net.Coffee 信誉分降序，未知信誉排最后；
     - 所有落地节点（`_USAI`、`_Lnd`、`_家宽` 或配置了 `dialer-proxy`）一律置于该地区最末尾；
     - 整个地区位置全部确定后，才从 1 开始依次递增重新编号（不改任何前缀与后缀）。

4. **模版一致性与策略组规则同步 (严格同步 freenode 规范)**：
   - **`🛡️ Front前置`**：`["⚡ Fast自动选择", "DIRECT"] + [所有 Key 节点名称]`。若本批无 Key 节点则使用备用前置，再降级为可用直连节点。**落地节点绝对禁止进入前置跳板组**。
   - **`⚡ Fast自动选择`**：`url-test`，优先所有 Key；无 Key 时与前置组使用相同的备用前置池，再回落到可用直连节点或 `DIRECT`，绝不包含落地。
   - **`🔒️ 落地节点`**：自动归集所有落地节点，Clash/Mihomo 注入 `dialer-proxy: "🛡️ Front前置"`，sing-box 注入 `detour: "🛡️ Front前置"`。
   - **母版原文渲染**：母版为技能内 `templates/template.yaml`（格式对齐 freenode，可手动修改），导出只替换 `proxies` / `proxy-groups` 两段，注释与空行逐字保留；测试开始前先校验母版语法与规则引用。详见 [config-rendering.md](references/config-rendering.md) 第 5 节。
   - **双份配置同步导出**：`probe_singbox.py` 结束时同时生成 sing-box（`.json`）与 Clash/Mihomo（`.yaml`）；`probe_services.py` 只导出 `.yaml`；`convert_dual.py` 可将现有 sing-box JSON 或 Clash/Mihomo YAML 规范化并同步导出两种格式。两份配置结构同步，均包含 17 个标准策略组（前置、自动、手动、综合全通、AI、Google、流媒体、落地节点等）与分流规则。

## 常用 CLI 命令

所有脚本位于 `<skill>/scripts/` 目录下（`<skill>` 为当前技能根目录）：

```bash
# 1. 默认标准全量测试 (不测速: IP、AI、免盾、YouTube免登、3秒防断流、打标与配置导出)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --report <报告.json>

# 2. 用户主动要求测速时: 完整下载测速 (稳态 < 6 Mbps 删除) 与 Key 优质跳板评选 (本地/Actions 自动选 Profile)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --speed-test

# 3. 本地开有 TUN 代理 (如 Karing/Clash Verge) 时：物理网卡自动探测，也可显式指定
python <skill>/scripts/probe_services.py --input <输入源> --speed-test --iface WLAN --output <输出.yaml>

# 4. 轻量模式 (跳过浏览器，仅执行接口测试与防断流快检)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --no-browser

# 5. 备用流水线 (仅用户要求 sing-box 内核或 sing-box JSON 成品时): sing-box 内核测试并双份导出
python <skill>/scripts/probe_singbox.py --input <输入.json> --output <输出.json> --speed-test --batch-size 20

# 6. 用户主动要求重排序/重编号时 (两条流水线均支持；默认保留原节点编号)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --resort

# 7. 用户仅要求属地抽查时：20节点多源复核（不测速、不改输入，ip.cx 作为留出来源）
python <skill>/scripts/audit_geolocation.py --input <配置.yaml> --report <复核.json> --count 20 --mihomo <内核路径> --iface WLAN --include "🇸🇬 ❇️新加坡_4"

# 8. 现有 sing-box JSON 或 Clash/Mihomo YAML 规范化并双份导出
python <skill>/scripts/convert_dual.py --input <输入.json或.yaml> --output-json <输出.json> --output-yaml <输出.yaml>

# 9. 用户主动要求空间测绘搜索最新订阅源并提取节点 (默认 FoFa + 360 Quake 双引擎协同去重)
python <skill>/scripts/fofa_search.py --output spatial_proxies.yaml

# 10. 指定单引擎或专项语法 (如 仅 Quake / 仅 FoFa / Hysteria 2 / VLESS)
python <skill>/scripts/fofa_search.py --engine quake --preset recommended --output quake_proxies.yaml
python <skill>/scripts/fofa_search.py --engine fofa --preset hy2 --output hy2_proxies.yaml
python <skill>/scripts/fofa_search.py --engine quake --quake-query 'status_code: 200 AND response: "vless"' -o vless.yaml

# 11. 一键抓取并直接联动全量服务能力测试与配置渲染
python <skill>/scripts/fofa_search.py --probe --output final.yaml
# 或主流水线直接传入测绘源:
python <skill>/scripts/probe_services.py --input spatial:recommended --output final.yaml
python <skill>/scripts/probe_services.py --input quake:recommended --output final.yaml

# 12. 测活测速并直接合流并入现有目标订阅配置 (默认保留底库原节点及编号，新节点补空号排位)
python <skill>/scripts/probe_services.py --input <输入源> --merge-into <底库.yaml>
python <skill>/scripts/fofa_search.py --probe --merge-into <底库.yaml>

# 13. 合流时启用中间插入模式 (打破原编号完全重排序并重新连续编号)
python <skill>/scripts/probe_services.py --input <输入源> --merge-into <底库.yaml> --insert
# 或离线合并现有配置:
python <skill>/scripts/merge_configs.py --base <底库.yaml> --add <待并入.yaml> [--insert] --apply
```

## 按需查阅

- **空间测绘订阅搜索、Quake 语法优化与多源节点提取**：读 [fofa-subscription-search.md](references/fofa-subscription-search.md)。
- **IP 属地升级、送中处理与抽查证据规则**：读 [geolocation.md](references/geolocation.md)。
- **测试判据与详细规范**：读 [testing-criteria.md](references/testing-criteria.md)。
- **运行环境、内核配置、TUN 共存与 GitHub Actions 云端运行**：读 [runner-environment.md](references/runner-environment.md)；工作流模板见 [node-probe.yml](assets/github-actions/node-probe.yml)。
- **策略组映射与 YAML 配置渲染**：读 [config-rendering.md](references/config-rendering.md)。
- **用户明确要求检测真实出口 / 落地 IP（`probe.py`、`recheck.py`）**：读 [egress-probing.md](references/egress-probing.md)。
- **不联网的本地排序、重命名与配置合并**：读 [local-operations.md](references/local-operations.md)。
- **TUN 污染、出口重合等实战故障排查**：读 [troubleshooting.md](references/troubleshooting.md)。
