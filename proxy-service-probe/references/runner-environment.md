# 运行环境与多客户端安全共存指南

本文档说明技能所需的底层运行时环境、Mihomo 内核定位策略、Playwright 浏览器配置，以及在本地开启多种代理客户端（Karing、Sing-box、Mihomo 系列、Xray 等）时的安全隔离与防断网保护方案。

---

## 1. 基础运行依赖

- **Python**: 3.9 及以上版本。
- **必要 Python 包**：
  ```bash
  pip install pyyaml requests pycountry playwright
  ```
- **Playwright 浏览器安装**：
  ```bash
  python -m playwright install chromium
  ```
  > **注意**：必须安装完整 Chromium（新无头模式，`channel="chromium"`），不能仅安装 `headless-shell`，否则容易触发 Google / YouTube 的机器人风控。
- **测速不依赖外部命令行工具**：持续下载测速由 Python 单连接流式读取完成，不再调用 `curl`、不写临时文件。

---

## 2. Mihomo 内核查找与生命周期

测试脚本通过启动临时的轻量级 Mihomo 守护进程对各个节点开放本地混合（Mixed HTTP/SOCKS5）端口进行测探。

### 内核寻找优先级
1. 命令行参数 `--mihomo <path>` 显式指定。
2. 环境变量 `MIHOMO_BIN` 指定的路径。
3. 工作目录或上级目录的 `_temp/mihomo.exe` 或 `_temp/mihomo`。
4. 技能自带内核：Windows 为 `<skill>/core/mihomo.exe`，Linux（如 GitHub Actions）为 `<skill>/core/mihomo`（需可执行权限）。
5. 环境变量 `PATH` 中的 `mihomo.exe` 或 `mihomo`。

---

## 3. 多客户端安全共存与防破坏方案 (Karing / Sing-box / Mihomo / Xray)

在日常使用中，开发者本地通常开着日常代理客户端（如 Karing、Sing-box、Clash Verge、Mihomo Party、v2rayN/Xray 等），并可能启用了系统代理或 TUN 模式。为确保测试和测速流水线**绝不干扰、破坏或降级用户的现有网络环境**，本技能遵循以下严格安全准则：

### 3.1 端口冲突黑名单与动态分配
- **常见默认端口冲突隐患**：
  - Mihomo / Clash: `7890` (HTTP/Mixed), `7891` (SOCKS), `9090` (Clash API)
  - Sing-box: `2080` (Mixed), `10808` (SOCKS), `10809` (HTTP)
  - Karing: `3067` (SOCKS), `24999` (Mixed)
  - Xray / v2rayN: `10808` (SOCKS), `10809` (HTTP)
  - DNS: `53`, `1053`, `5353`
- **防护措施**：
  - 脚本内置 `BLACKLIST_PORTS` 集合，动态端口探测器（`get_free_port`）在申请本地可用端口时，强制跳过上述所有已知端口。
  - 所有测试实例均在 `127.0.0.1` 动态申请高位临时空闲端口，测试完成后立即释放。

### 3.2 零修改系统代理与注册表
- 绝不碰触 Windows 注册表 IE 代理设置（`ProxyEnable` / `ProxyServer`）。
- 绝不修改系统路由表（`route add/delete`）。
- 所有 Python 测试请求（含持续下载测速）显式声明 `trust_env = False`，不继承系统代理环境变量，确保仅走本次指定的临时端口。

### 3.3 TUN 模式穿透与物理网卡自动绑定
- **TUN 劫持隐患**：
  - 若用户开着 TUN（如 Karing TUN 或 Clash TUN），本地对外发起的连接会被虚拟网卡拦截，导致跑机自身公网出口被误判为代理节点的境外出口，触发“出口与本机重合”误杀。
- **防护措施**：
  1. 测试内核配置强制关闭 TUN（`tun: {enable: false}`）；
  2. **活跃物理网卡自动探测**：脚本在 Windows 下通过 PowerShell 自动扫描当前状态为 `Up` 的物理网卡名称（如 `WLAN` 或 `以太网`，自动排除含 `TUN`、`Virtual`、`Karing`、`Sing-box`、`Clash` 的虚拟网卡）；
  3. 将物理网卡名称写入内核配置的 `interface-name`（如 `interface-name: WLAN`），强制节点测试流量直接从物理网卡发出，彻底穿透并绕开系统 TUN 虚拟网卡；
  4. **跑机基线同路径测得**：基线出口经 mihomo DIRECT 监听（绑定同一物理网卡）探测；系统路由出口若与之不同，说明本机客户端正经 TUN/系统代理使用某个节点，该出口只记录、不作基线，正在使用的节点照常测试。`--direct-proxy` 可显式指定基线探测代理。
  5. **sing-box 备用流水线的物理直连中继**：sing-box 1.14 在 Windows 外部 TUN 下 `bind_interface` / `default_interface` 不可靠。有确定物理网卡时统一启动绑定该网卡的 mihomo DIRECT SOCKS 中继（支持 TCP/UDP），节点出站与前置经其中转，落地经自身前置。不能按回显 IP 是否相同来决定启用，因为本机客户端可能将回显站点分流直连。中继启动失败即停止测试，不降级走 TUN；无网卡信息（如默认 Linux CI）时不启用中继。

### 3.4 带宽上限与测速隔离 (准确性优先，兼顾本机网络)
- 带宽上限必须不低于 Key 门槛：本地默认 `--rate-limit-mbps 40`（Key 门槛 12 Mbps），低于门槛直接报错，不会静默给出"全部不达标"。
- 服务线（默认并发 4）与测速线交错并行，节点一测活就入队；本地测速严格串行。同一节点及其前置由调度器隔离，避免测速和服务同时占用同一链路。
- 两种内核的本机 Clash API `/traffic` 接入同一流量监测；未达标且受并行流量干扰的测速等服务线结束后重测。流量证据缺失时按服务活动保守判定，不把受干扰低速直接当淘汰依据。
- 单节点观测 10~20 秒（快节点与明显过慢的节点约 10 秒，爬升慢或贴近门槛的节点到 20 秒，贴近门槛再重测一次），40 Mbps 上限下单次最多约 100MB。
- 本机宽带下行低于带宽上限时，测速结果受本地线路限制；运行结束若无节点达标会给出提示。

### 3.5 进程生命周期守护
- 两种内核共用上下文管理器与 `finally` 清理：先 `terminate` 并等待，超时再 `kill`，进程结束后删除临时目录。
- 一个节点配置被拒时自动二分隔离，保留其它正常监听；控制接口仅监听回环且带随机密钥。

---

## 4. 模式说明：标准全量模式 vs 测速模式 vs 降级模式

- **标准全量模式（默认，不测速）**：
  - 默认启动全量服务测试（IP属地、AI三大全通、Playwright Chromium YouTube 免登录实播 >=10s、4 站免盾检测、国际流媒体解锁）。
  - 执行 3 秒轻量防断流快检（<16KB 淘汰）。
  - **不执行** Sustained 下载测速，不评选 Key。
  - 符合标准的节点授予 `✨️` 徽章。

- **完整测速模式（主动要求 `--speed-test`）**：
  - 节点判活后同时进入完整服务线与测速线；落地测速等待前置带宽/出口证据，最终统一核对（稳态 < 6 Mbps 删除、>= 12 Mbps 且最低 >= 6 Mbps 授 Key/Fast，详见 testing-criteria.md 5.3）。
  - 激活 Key 优质前置跳板遴选与配额分配（过滤 HTTP/SOCKS，按强加密与亚太核心区优先打分）。
  - 节点前置标识自动注入 `Key`（前置跳板）或 `Fast`（高速直连/落地节点）。
  - 策略组同步生成包含 Key 节点的 `🛡️ Front前置` 与 `⚡ Fast自动选择`。

- **轻量降级模式（仅限显式指定 `--no-browser`）**：
  - 跳过 Playwright Chromium 浏览器实测（省略 YouTube 与 4 站浏览器免盾）。
  - 保留 IP 属地、AI 接口、流媒体与防断流快检。

---

## 5. 运行环境 Profile：本地与 GitHub Actions

同一套代码、测试项目与合格判据，`--profile auto`（默认）按环境自动选择资源参数：检测到 `GITHUB_ACTIONS=true` 或 `CI=true` 时为 `ci`，否则为 `local`。命令行显式参数始终优先。两种运行方式各自完整执行，不拆分为"云端粗筛 + 本地精测"。

| 项目 | local（本地） | ci（GitHub Actions） |
|---|---|---|
| 测速带宽上限 | 40 Mbps | 50 Mbps（受 Cloudflare 备用目标 50MB 载荷约束） |
| 测速并发 | 1（严格串行） | 2 |
| 物理网卡绑定 | Windows 自动探测防 TUN 劫持 | Linux 无 TUN，不绑定 |
| 观测位置 (`vantage`) | 本机网络 → 节点 → CDN | 云端机房 → 节点 → CDN |
| 门槛 / 观测窗 / 评选规则 | 相同 | 相同 |

### 5.1 GitHub Actions 运行
- 模板：[assets/github-actions/node-probe.yml](../assets/github-actions/node-probe.yml)，复制到**私有**仓库的 `.github/workflows/`，按实际目录修改 `SKILL_DIR`。
- 订阅放在仓库 Secret `NODE_SOURCE`（订阅 URL 或节点原文）。
- 工作流安装 Python 依赖与 Playwright Chromium，下载固定版本的 Linux Mihomo 并做 sha256 校验后放到 `<skill>/core/mihomo`。
- 公开仓库的日志与 Artifact 会泄露节点名与出口 IP，工作流在公开仓库中直接失败；结果以 Artifact 形式保存 7 天，不发布到 Release。
- 云端结论反映节点出口到 CDN 的能力（能否稳定承载高码率视频、是否先突发后限速），不代表国内网络到节点的线路质量；需要反映本机线路时在本地运行。
