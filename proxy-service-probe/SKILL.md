---
name: proxy-service-probe
description: 对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登实播、免盾过盾、流媒体、打标命名、本地测速与Key节点筛选及Clash/Mihomo配置渲染）时使用。
---

# 代理节点服务能力测试与配置渲染 (proxy-service-probe)

对代理节点（Clash YAML、sing-box JSON、节点订阅链接或 URI）执行全方位的服务能力检测、智能淘汰断流与失效节点、生成规范化角色与能力标签，并依据项目级 `template.yaml` 渲染导出完整的 Clash/Mihomo 订阅配置文件。

## 核心契约

> [!IMPORTANT]
> **默认行为准则**：
> 1. **全量服务检测**：本技能默认执行涵盖 IP 属地、AI 三大平台解锁、Playwright Chromium YouTube 免登录实播、4 站免盾检测与国际流媒体解锁。严禁擅自启用轻量模式；`--no-browser` 仅作为用户显式指定或系统无浏览器环境时的降级保底选项。
> 2. **测速非主动技能契约**：**节点持续下载测速为非主动技能**。默认流水线仅执行 3 秒轻量防断流快检（<16KB 淘汰）；**仅当用户明确主动要求**（如指令中包含“测速”、“测试节点速度”、“测速筛选”或显式传入 `--speed-test`）时，才启动完整本地持续下载测速流水线并执行 Key 节点遴选与打标。

1. **测试范围与判定依据**：
   - **IP 属地与出口**：HTTPS 双栈出口及前后复核；Gemini 显式地区码优先、YouTube 双标记一致才兜底；IPinfo、ipwho.is、ipapi.is、DB-IP 按实际出口绑定交叉验证，Cloudflare `loc` 仅作辅助、`colo` 不参与定国。普通强分歧不强改国旗；送中/受限地区污染沿用实际属地 + `_⚠️CN` 等标记，剥离 AI 全通资格。Net.Coffee 仅保留 IP 绑定成功的信誉信息。详见 [geolocation.md](references/geolocation.md)。
   - **AI 解锁**：ChatGPT/OpenAI（合规端点 200 + 移动端/模型端点连通）、Claude（模型端点 401 判通）、Gemini（页面可用性标志 `[45631641,null,true]` 实测）；三项通过且出口稳定非送中标记为“AI三大全通”。
   - **YouTube 免登录实播**：Playwright Chromium 真实无头环境，注入 HTML5 播放观察者（实播 >= 10 秒、非缓冲停滞、非人机验证 / bot_required），播放前后双向复核浏览器出口 IP，通过 2 个视频判定免登实播达标。
   - **过盾 / 免盾**：HTTP 初查 + 浏览器针对 4 站（Cloudflare 官网、ChatGPT、Claude、Gemini）的质询检测，4 站观测齐全且至多 1 站遇到挑战（且自动解除）判定为免盾。
   - **流媒体与防断流**：Netflix（非自制剧 200）、Disney+ 页面可用性；默认 3 秒流式下载窗口防断流检测，累计传输不足 16KB 判定为断流假死并淘汰。
   - **本地持续下载测速 (主动触发)**：基于 `curl` 与 `RateMeter` 逐秒采样，统计中位数（`median_mbps`）、P10 速率与最大卡顿。达标门槛：中位数 >= 5.0 Mbps、P10 >= 3.0 Mbps、卡顿 <= 1.0s。

2. **多客户端防破坏与安全隔离方案 (兼容 Karing / Sing-box / Mihomo / Xray)**：
   - **零系统破坏**：严禁碰触 Windows 注册表 IE 代理设置（`ProxyEnable`/`ProxyServer`）及系统路由表。测试流量 100% 局限在本地环回端口。
   - **动态端口避让**：自动避让已知客户端常用端口黑名单（`7890-7895, 9090, 2080-2081, 3067, 10808-10809, 24999`），所有批次严格申请动态空闲端口，杜绝端口冲突导致用户客户端崩溃。
   - **物理网卡绑定防 TUN 劫持**：Windows 下自动检测当前联网活跃物理网卡（如 `WLAN` 或 `以太网`，排除 Karing/Singbox/Clash 的虚拟 TUN 网卡），测试内核配置关闭 TUN（`tun: {enable: false}`）并注入 `interface-name`，直连基线探测支持 `--direct-proxy`，彻底防止跑机出口被 TUN 接管导致“出口重合”误杀。
   - **限速保护防网络拥塞**：测速默认强制限速（`--rate-limit-mbps 10`），绝不占满家宽，保障用户本地正常的会议、视频或网页浏览不卡顿。

3. **Key 优质前置跳板遴选与打标体系**：
   - **Key 准入硬门槛**：
     - 严禁 `http`、`https`、`socks`、`socks5` 作为 Key（因无加密或不支持非 443 端口 CONNECT，无法中转非标端口落地节点）；
     - 落地节点（`_Lnd`, `_USAI`）绝不可作为前置跳板；
     - 出口必须真实出网且不与本地跑机基线 IP 重合；
     - 必须通过持续下载测速（中位数 >= 5.0 Mbps）。
   - **Key 优选与配额**：TLS-TCP 强加密加分，亚太核心区（`HK`, `TW`, `JP`, `SG`, `KR`）优先加分，并执行区域配额限制。
   - **打标与规范命名体系**：
     - 前置标识顺序：严格为 `[国旗] [❇️] [✨️] [Key / Fast] [国家]_[编号][落地后缀][流媒体后缀][来源后缀]`。
     - `❇️`：AI 三大全通。
     - `✨️`：综合全通能力徽章（AI三大通过 + YouTube免登录实播通过 + 四站免盾）。
     - `Key`：评选出的优质前置跳板节点（如 `🇯🇵 ❇️✨️Key日本_1`, `🇺🇸 ❇️Key美国_1_NF`）。
     - `Key` 与 `Fast` 严格互斥；未开启测速或未达标节点不带 Key/Fast 标签。
   - **地区内部位阶排序准则**：
     - 同地区内严格按「直连优选 → 直连普通 → 落地沉底」排列；
     - 直连优选顺位严格遵循：`✨️ > ❇️ > Key > Fast > _NF > _D+`；
     - 所有落地节点（`_USAI`、`_Lnd`、`_家宽` 或配置了 `dialer-proxy`）一律置于该地区最末尾；
     - 排序确定后，每个国家/地区严格从 1 开始依次递增重新编号（不改任何前缀与后缀）。

4. **模版一致性与策略组规则同步 (严格同步 freenode 规范)**：
   - **`🛡️ Front前置`**：`["⚡ Fast自动选择", "DIRECT"] + [所有 Key 节点名称]`。若本批无 Key 节点则安全降级为可用直连节点。**落地节点绝对禁止进入前置跳板组**。
   - **`⚡ Fast自动选择`**：`url-test` 自动选优，成员仅包含 `[所有 Key 节点名称]`（回落为 `["DIRECT"]`）。
   - **`🔒️ 落地节点`**：自动归集所有落地节点，并强制注入 `dialer-proxy: "🛡️ Front前置"`（或指定的前置跳板）。
   - **双份配置一键同步导出**：每次测试流水线结束导出时，默认同时生成标准 sing-box 格式文件（`.json`）与标准 Clash/Mihomo 格式文件（`.yaml`）。两份配置文件结构完全同步，均包含完整的 17 个标准策略组（前置、自动、手动、综合全通、AI、Google、流媒体、落地节点等）与精细分流规则体系。

## 常用 CLI 命令

所有脚本位于 `<skill>/scripts/` 目录下（`<skill>` 为当前技能根目录）：

```bash
# 1. 默认标准全量测试 (不测速: IP、AI、免盾、YouTube免登、3秒防断流、打标与配置导出)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --report <报告.json>

# 2. 用户主动要求测速时: 开启完整下载测速、限速防卡顿、Key优质跳板评选与打标
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --speed-test --rate-limit-mbps 10

# 3. 本地开有 TUN 代理 (如 Karing/Clash Verge) 时的全保护测速
python <skill>/scripts/probe_services.py --input <输入源> --speed-test --iface WLAN --direct-proxy http://127.0.0.1:24999 --output <输出.yaml>

# 4. 轻量模式 (跳过浏览器，仅执行接口测试与防断流快检)
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --no-browser

# 5. sing-box 双轨全量服务测试与配置导出 (支持 --speed-test)
python <skill>/scripts/probe_singbox.py --input <输入.json> --output <输出.json> --front-proxy 127.0.0.1:3067 --batch-size 20
# 6. 用户仅要求属地抽查时：20节点多源复核（不测速、不改输入，ip.cx 作为留出来源）
python <skill>/scripts/audit_geolocation.py --input <配置.yaml> --report <复核.json> --count 20 --mihomo <内核路径> --iface WLAN --include "🇸🇬 ❇️新加坡_4"
```

## 按需查阅

- **IP 属地升级、送中处理与抽查证据规则**：读 [geolocation.md](references/geolocation.md)。
- **测试判据与详细规范**：读 [testing-criteria.md](references/testing-criteria.md)。
- **运行环境、内核配置与 TUN 共存**：读 [runner-environment.md](references/runner-environment.md)。
- **策略组映射与 YAML 配置渲染**：读 [config-rendering.md](references/config-rendering.md)。
