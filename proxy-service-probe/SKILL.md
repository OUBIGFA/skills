---
name: proxy-service-probe
description: 对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登实播、免盾过盾、流媒体、打标命名、本地测速与Key节点筛选、配置合并/转换及Clash/Mihomo配置渲染，以及用户主动触发时的FoFa/Quake空间测绘与GitHub Gist订阅搜索与节点提取）时使用。
---

# 代理节点服务能力测试与配置渲染

对 Clash YAML、sing-box JSON、订阅链接或节点 URI 做服务能力检测，淘汰断流与失效节点，按规范打标命名，并以 `templates/template.yaml` 渲染导出 Clash/Mihomo（及可选 sing-box）配置。

## 流水线选择

- **主流水线 `probe_services.py`（mihomo）**：默认一律使用，支持全部输入格式、本地/GitHub Actions Profile 与云端运行。
- **备用流水线 `probe_singbox.py`（sing-box）**：仅当用户要求用 sing-box 内核验证兼容性，或需要直接产出 sing-box JSON 时使用。
- 两者共用 `core.probe_flow`：并发测活 → 服务检测线（默认并发以代码为准）∥ 下载测速线（本地串行，仅开启测速时）→ 统一核对与导出。节点一判活就入队，不等整批完成。

## 默认契约

> [!IMPORTANT]
> 1. **全量服务检测**：默认执行 IP 属地、AI 全平台、Playwright YouTube 免登实播、多站免盾、流媒体与防断流快检。不得擅自用轻量模式；`--no-browser` 仅在用户指定或系统无浏览器时降级使用。
> 2. **测速需主动触发**：默认只做防断流快检（低于代码淘汰线则淘汰），不授 Key/Free/Fast。用户明确要求“测速 / 测试节点速度 / 测速筛选”或传 `--speed-test` 时，才跑完整持续下载测速与 Key 遴选。本地与 Actions 同一套代码与判据，`--profile auto` 自动选资源参数，两处各自独立完整运行，不做云端粗筛 + 本地精测。
> 3. **编号稳定**：默认保留原节点编号（属地未变不改号），新节点按国家补空号。仅当用户明确要求重排序/重编号时传 `--resort`，且先定位置再从 1 编号。
> 4. **订阅搜索需主动触发**：FoFa / 360 Quake / GitHub Gist 搜索只在用户明确要求“搜索订阅”，或显式调用 `fofa_search.py` / `gist_search.py`、传入 `--input fofa:|quake:|spatial:|gist:...` 时启动；默认流水线绝不主动扫描或检索。默认预设 `residential`（家宽、双 ISP、高纯净度），超过单订阅源节点上限自动丢弃（阈值以代码与配置为准）。配置分别在 [fofa_config.json](fofa_config.json)（本地私密，模板见 [fofa_config.example.json](fofa_config.example.json)）与 [gist_config.json](gist_config.json)。
> 5. **合流并入**：`--merge-into` 默认保留底库原节点与原编号，新节点按国家补空号并按地区聚拢；仅当用户要求中间插入（`--insert` 或 `--resort`）时，才完整重排并从 1 连续编号。
> 6. **默认重点地区（长期生效，无需用户重复提醒）**：搜索抓取、候选排序、`Key` 优选与结果汇总自动把 **高质量的美国节点（`US`：AI 全通 `❇️`/`_USAI`、家宽/双 ISP `🏠`/`_ISP`、高纯净 `♥️`、综合全通 `✨️`、流媒体全解）** 与 **高速直连的香港、台湾、日本、新加坡节点（`HK / TW / JP / SG`：直连、低延迟、低丢包、高稳态 `Key`/`Fast`，并作为 `Key` 前置跳板首选）** 作为重点目标。严守以实测为准，不凭原名直接授标。

## 检测范围速览

| 维度 | 关键判据 | 细节 |
|---|---|---|
| 测活与丢包 | 多端点轮换采样；丢包率超淘汰线淘汰，中度丢包保留但不可作 Key、剥离 ✨️（阈值以代码为准） | [testing-criteria.md](references/testing-criteria.md) |
| IP 属地 | 按真实出口绑定 IPinfo / ipwho.is / ipapi.is / DB-IP 与 Gemini、YT 信号；分歧优先取全源有效票严格多数；平票且纯 GeoIP 有共识时以 GeoIP 为准；平票无共识或无其他有效证据时以 Google 观测地区兜底；送中保留实际属地并标 `_⚠️CN` | [geolocation.md](references/geolocation.md) |
| 信誉与家宽 | 多源共识评分 + 网络层四级家宽真实检测（严禁盲信上游节点自标家宽/双ISP名称）；多出口取最低分与最严等级，缺证据记未知 | [testing-criteria.md](references/testing-criteria.md) §1.4 |
| AI 解锁 | OpenAI、Claude、Gemini、Hugging Face、Grok；Groq 仅作 ✨️ 条件 | §2 |
| YouTube | Playwright 连续实播达标、非缓冲停滞、非机器人验证，前后复核出口，多视频通过（时长与数量以代码为准） | §3 |
| 免盾 | OpenAI Sentinel、Google/YouTube、Reddit、TikTok、Cloudflare 多站联合评分 | §4 |
| 流媒体 / 防断流 | Netflix 非自制剧、Disney+；防断流快检低于代码阈值淘汰 | §5.1–5.2 |
| 持续测速（主动） | 持续下载观测稳态与最低速率：达标授 Key/Fast 级，低于淘汰线删除，贴近门槛重测一次（窗口与速率门槛以代码为准） | §5.3 |
| 直连 / 需前置 | 首轮不通者经多个已判活前置复测；最终必须保留至少一条已验证落地链路才导出 | §5.5 |

## 安全隔离

- 不修改 Windows 注册表代理（`ProxyEnable` / `ProxyServer`）与系统路由；测试流量只走本地环回端口。
- 避让常见客户端端口（`7890-7895, 9090, 2080-2081, 3067, 10808-10809, 24999`），一律申请动态空闲端口。
- 测试内核关闭 TUN；Windows 自动探测物理网卡并绑定。sing-box 有网卡时经 mihomo DIRECT 中继出网，中继失败即停止，不悄悄改走 TUN。
- 测速上限不低于合格门槛（本地与云端参数以代码 Profile 为准）；同一节点及其前置不同时被测速与服务占用。

详见 [runner-environment.md](references/runner-environment.md)。

## 打标、编号与配置

- 命名结构：`[国旗] [✨️] [🏠 / ♥️] [❇️] [Key / Free / Fast] [国家][_城市]_[编号][_IPLC 或 _ISP][落地][流媒体][来源][污染标记]`。
- 前缀顺序 ✨️ > 🏠 > ❇️ > Key > Fast；🏠 与 ♥️ 互斥，且 🏠 真家宽节点专作高纯净出口、不参与 `[Key]` 前置跳板评选；Key/Free 与 Fast 互斥且只在主动测速达标时授予；`[⚡WARP]` 节点剥夺 `🏠`/`♥️`/`✨️` 但保留 AI 解锁标记（`❇️`/`_USAI`/`_GOAI`）。
- 链式落地（`_Lnd` 或实测需前置的 `_USAI` / `_GOAI`）沉底并注入 `dialer-proxy: "🛡️ Front前置"`（sing-box 为 `detour`）；直连 USAI/GOAI 与 🏠/`_ISP` 家宽不沉底。
- 落地节点不得进入 `🛡️ Front前置` 或 `⚡ Fast自动选择`；无 Key 时使用已验证的备用前置，再回落直连节点或 `DIRECT`。
- 导出只替换母版的 `proxies` / `proxy-groups`，其余注释与空行逐字保留；测试前先校验母版。`probe_services.py` 导出 `.yaml`，`probe_singbox.py` 与 `convert_dual.py` 同时导出 `.json` 与 `.yaml`。

徽章判据、Key 准入、默认编号、`--resort` 排序与示例见 [naming-and-sorting.md](references/naming-and-sorting.md)；策略组成员与母版规则见 [config-rendering.md](references/config-rendering.md)。

## 常用命令

脚本位于 `<skill>/scripts/`：

```bash
# 默认全量测试（不测速）
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --report <报告.json>

# 用户主动要求测速：完整测速 + Key 遴选；本机开 TUN 时可显式指定网卡
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --speed-test [--iface WLAN]

# 降级：跳过浏览器（仅用户指定或无浏览器环境）
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --no-browser

# 用户要求重排序/重编号
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --resort

# 合流并入底库（默认保留原编号；--insert 完整重排）
python <skill>/scripts/probe_services.py --input <输入源> --merge-into <底库.yaml> [--insert]
python <skill>/scripts/merge_configs.py --base <底库.yaml> --add <待并入.yaml> [--insert] --apply

# 备用流水线：sing-box 内核测试并双份导出
python <skill>/scripts/probe_singbox.py --input <输入.json> --output <输出.json> --speed-test --batch-size 20

# 仅属地抽查（不测速、不改输入）
python <skill>/scripts/audit_geolocation.py --input <配置.yaml> --report <复核.json> --count 20 --mihomo <内核路径> --iface WLAN

# 现有配置规范化并双份导出
python <skill>/scripts/convert_dual.py --input <输入.json或.yaml> --output-json <输出.json> --output-yaml <输出.yaml>

# 用户主动要求搜索订阅（可加 --probe 直接联动测试，或 --merge-into 并入底库）
python <skill>/scripts/fofa_search.py --output spatial_proxies.yaml
python <skill>/scripts/fofa_search.py --engine quake --preset residential --output quake_residential.yaml
python <skill>/scripts/gist_search.py --preset subs --output subs_proxies.yaml
python <skill>/scripts/probe_services.py --input spatial:residential --output final.yaml
python <skill>/scripts/probe_services.py --input gist:residential --output final.yaml
```

完整参数以 `--help` 为准。

## 按需查阅

- 测试判据、测速与前置/落地细则：[testing-criteria.md](references/testing-criteria.md)
- 打标、Key 准入、编号与排序：[naming-and-sorting.md](references/naming-and-sorting.md)
- IP 属地、送中处理与抽查证据：[geolocation.md](references/geolocation.md)
- 运行环境、内核、TUN 共存与 GitHub Actions：[runner-environment.md](references/runner-environment.md)，工作流模板 [node-probe.yml](assets/github-actions/node-probe.yml)
- 策略组映射与 YAML 渲染：[config-rendering.md](references/config-rendering.md)
- FoFa / Quake 空间测绘搜索：[fofa-subscription-search.md](references/fofa-subscription-search.md)
- GitHub Gist 订阅搜索：[gist-subscription-search.md](references/gist-subscription-search.md)
- 用户明确要求检测真实出口（`probe.py`、`recheck.py`）：[egress-probing.md](references/egress-probing.md)
- 不联网的本地排序、重命名与合并：[local-operations.md](references/local-operations.md)
- TUN 污染、出口重合等故障：[troubleshooting.md](references/troubleshooting.md)
