# 运行环境与 TUN 共存指南

本文档说明技能所需的底层运行时环境、Mihomo 内核定位策略、Playwright 浏览器配置以及在开启 TUN 客户端（如 Karing、Clash Verge 等）时的防污染解决方案。

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

---

## 2. Mihomo 内核查找与生命周期

测试脚本通过启动临时的轻量级 Mihomo 守护进程对各个节点开放本地混合（Mixed HTTP/SOCKS5）端口进行测探。

### 内核寻找优先级
1. 命令行参数 `--mihomo <path>` 显式指定。
2. 环境变量 `MIHOMO_BIN` 指定的路径。
3. 工作目录或上级目录的 `_temp/mihomo.exe`（当前项目默认存放位置）。
4. 环境变量 `PATH` 中的 `mihomo.exe` 或 `mihomo`。

### 临时监听配置
- 脚本自动为每个批次在本地动态分配未占用的回环端口（如 `127.0.0.1:25000+`）。
- 节点实例默认关闭 TUN（`tun: {enable: false}`），仅监听在 `127.0.0.1`。
- 测试完成后，上下文管理器会自动优雅关闭内核子进程并释放端口。

---

## 3. Windows TUN / Karing 共存与防污染方案

在日常使用中，很多开发者的电脑上开着全局 TUN 代理（例如 Karing 或 Clash Verge 的 TUN 模式）。

### 痛点问题
1. **跑机基线出口污染**：直连请求（如测探跑机本身出口）会被系统 TUN 网卡接管，误以为跑机出口在境外（如美国），导致后续与节点比对时发生误判（判定为出口重合而淘汰）。
2. **DNS 抢答与泄露**：系统 DNS 请求被拦截。

### 解决方案
1. **绑定物理网卡（`--iface`）**：
   - 查阅当前联网的物理网卡名称（例如 `WLAN` 或 `以太网`）：
     ```powershell
     Get-NetAdapter | Where-Object Status -eq Up
     ```
   - 运行探测时传入参数 `--iface WLAN`。脚本生成的临时 Mihomo 配置会自动注入 `interface-name: WLAN`，确保代理流量走物理网卡发出，彻底绕开 TUN 虚拟网卡。
2. **配置直连基线监听（`--direct-proxy`）**：
   - 如果开启了系统代理或 TUN，起一个绑定物理网卡的 DIRECT 实例（如端口 `24999`），并通过参数 `--direct-proxy http://127.0.0.1:24999` 传入。
   - 基线出口探测（`probe_egress(None)`）将强制经由该直连监听发出，确保取得真实的本地家宽公网出口 IP。

---

## 4. 模式说明：标准全量模式 vs 降级模式

- **标准全量模式（默认）**：
  - 系统默认启动全量服务测试，利用 Playwright Chromium 执行 YouTube 真实无头免登实播（>=10s）与 4 站免盾检测，为综合表现优异的节点打上 `✨️` 徽章。
  - **严禁在用户未明确要求时默认跳过浏览器测试。**

- **降级模式（Graceful Degradation，仅限显式指定 `--no-browser`）**：
  - 仅当用户显式指定 `--no-browser`，或系统极端缺少 Playwright/Chromium 依赖时启用。
  - 脚本将降级为 **HTTP 纯净轻量模式**：
    - 完整执行：IP 真实出口、Google 地区判定、多源 GeoIP、Net.Coffee 纯净分、AI 三大平台接口测试、国际流媒体（Netflix/Disney+）及流式下载测速。
    - 跳过：YouTube 免登实播与浏览器免盾复核。
    - 节点标签保留 `❇️`、`Fast`、`_USAI` 等，省略依赖浏览器实播的 `✨️` 徽章。
