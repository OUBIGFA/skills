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
- **命令行工具**：系统需内置 `curl`（Windows 10/11 自带或 Git 附带）。

---

## 2. Mihomo 内核查找与生命周期

测试脚本通过启动临时的轻量级 Mihomo 守护进程对各个节点开放本地混合（Mixed HTTP/SOCKS5）端口进行测探。

### 内核寻找优先级
1. 命令行参数 `--mihomo <path>` 显式指定。
2. 环境变量 `MIHOMO_BIN` 指定的路径。
3. 工作目录或上级目录的 `_temp/mihomo.exe` 或 `_temp/mihomo`。
4. 环境变量 `PATH` 中的 `mihomo.exe` 或 `mihomo`。

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
- 所有 Python 测试请求显式声明 `trust_env = False`，curl 命令行显式指定 `--noproxy ""` 并清除代理环境变量，确保仅走本次指定的临时端口。

### 3.3 TUN 模式穿透与物理网卡自动绑定
- **TUN 劫持隐患**：
  - 若用户开着 TUN（如 Karing TUN 或 Clash TUN），本地对外发起的连接会被虚拟网卡拦截，导致跑机自身公网出口被误判为代理节点的境外出口，触发“出口与本机重合”误杀。
- **防护措施**：
  1. 测试内核配置强制关闭 TUN（`tun: {enable: false}`）；
  2. **活跃物理网卡自动探测**：脚本在 Windows 下通过 PowerShell 自动扫描当前状态为 `Up` 的物理网卡名称（如 `WLAN` 或 `以太网`，自动排除含 `TUN`、`Virtual`、`Karing`、`Sing-box`、`Clash` 的虚拟网卡）；
  3. 将物理网卡名称写入内核配置的 `interface-name`（如 `interface-name: WLAN`），强制节点测试流量直接从物理网卡发出，彻底穿透并绕开系统 TUN 虚拟网卡；
  4. 支持 `--direct-proxy http://127.0.0.1:24999`：对于基线出口探测，可指定走独立的本地直连监听，杜绝任何 TUN 污染。

### 3.4 宽带限速保护 (防 Bufferbloat 与应用卡顿)
- 当用户主动要求测速时（`--speed-test`），若不加限制地全速下载，极易把家庭宽带（28~100 Mbps）打满，导致用户正在进行的即时通信、视频会议或网页浏览丢包卡顿。
- **防护措施**：
  - 默认强制开启 `--rate-limit-mbps 10.0`（通过 curl `--limit-rate` 控制）；
  - 单节点测速时间窗口限制为 5.0 秒，单节点最大下载流量限制为 35 MB；
  - 既能测出节点是否具备高速中继能力，又对家庭网络总体负载控制在 20%~30% 以内，完全不影响正常使用。

### 3.5 进程生命周期守护
- 上下文管理器 + `atexit` 钩子双保险。
- 超时清理时严格执行“先终止内核进程（`proc.kill()`），再删除临时目录”的顺序，杜绝后台残留孤儿进程。

---

## 4. 模式说明：标准全量模式 vs 测速模式 vs 降级模式

- **标准全量模式（默认，不测速）**：
  - 默认启动全量服务测试（IP属地、AI三大全通、Playwright Chromium YouTube 免登录实播 >=10s、4 站免盾检测、国际流媒体解锁）。
  - 执行 3 秒轻量防断流快检（<16KB 淘汰）。
  - **不执行** Sustained 下载测速，不评选 Key。
  - 符合标准的节点授予 `✨️` 徽章。

- **完整测速模式（主动要求 `--speed-test`）**：
  - 在全量服务测试基础上，激活持续下载测速流水线与目标快速轻量预检（Range: 0-1023）。
  - 激活 Key 优质前置跳板遴选与配额分配（过滤 HTTP/SOCKS，按强加密与亚太核心区优先打分）。
  - 节点前置标识自动注入 `Key`（前置跳板）或 `Fast`（高速直连/落地节点）。
  - 策略组同步生成包含 Key 节点的 `🛡️ Front前置` 与 `⚡ Fast自动选择`。

- **轻量降级模式（仅限显式指定 `--no-browser`）**：
  - 跳过 Playwright Chromium 浏览器实测（省略 YouTube 与 4 站浏览器免盾）。
  - 保留 IP 属地、AI 接口、流媒体与防断流快检。
