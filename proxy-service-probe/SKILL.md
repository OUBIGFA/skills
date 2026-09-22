---
name: proxy-service-probe
description: 对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登实播、免盾过盾、流媒体、打标命名及Clash/Mihomo配置渲染）时使用。
---

# 代理节点服务能力测试与配置渲染 (proxy-service-probe)

对代理节点（Clash YAML、sing-box JSON、节点订阅链接或 URI）执行全方位的服务能力检测、智能淘汰断流与失效节点、生成规范化角色与能力标签，并依据项目级 `template.yaml` 渲染导出完整的 Clash/Mihomo 订阅配置文件。

## 核心契约

> [!IMPORTANT]
> **默认行为准则**：本技能默认且必须执行**全量服务检测**（涵盖 IP 属地、AI 三大平台解锁、Playwright Chromium YouTube 免登录实播、4 站免盾检测、国际流媒体解锁与测速）。严禁擅自启用轻量模式；`--no-browser` 仅作为用户显式指定或系统无浏览器环境时的降级保底选项。

1. **测试范围与判定依据**：
   - **IP 属地与出口**：双栈真实出口探测；Google 自身地区码判定（Gemini 页面内嵌 ISO 地区码优先，YouTube Premium 兜底）；多源 GeoIP 投票（ipwhois、ip.sb、Net.Coffee）；Net.Coffee 欺诈信誉分与网络属性（机房/家宽/代理/爬虫）；送中（Google Mainland CN）拦截标记。
   - **AI 解锁**：ChatGPT/OpenAI（合规端点 200 + 移动端/模型端点连通）、Claude（模型端点 401 判通）、Gemini（页面可用性标志 `[45631641,null,true]` 实测）；三项通过且出口稳定非送中标记为“AI三大全通”。
   - **YouTube 免登录实播**：Playwright Chromium 真实无头环境，注入 HTML5 播放观察者（实播 >= 10 秒、非缓冲停滞、非人机验证 / bot_required），播放前后双向复核浏览器出口 IP，通过 2 个视频判定免登实播达标。
   - **过盾 / 免盾**：HTTP 初查 + 浏览器针对 4 站（Cloudflare 官网、ChatGPT、Claude、Gemini）的质询检测，4 站观测齐全且至多 1 站遇到挑战（且自动解除）判定为免盾。
   - **流媒体与带宽**：Netflix（非自制剧 200）、Disney+ 页面可用性；1.5~3 秒流式下载窗口带宽测试，断流假死判定默认以 `< 16KB`（平稳传输基线）为准，避免误杀可用的低速 AI/文本节点；高速节点（>= 500KB/s）标 `Fast`。
   - **前置跳板与落地链式测试（双轨自适应超时）**：
     - 直连节点（1-hop）探测超时设为 2.0s~2.5s。
     - 落地/中转节点经由本地前置代理（如 Karing SOCKS5 `127.0.0.1:3067`）建立多跳链路，建连与 TLS Reality 握手通常耗时 2.3s~3.5s，探测超时**必须放宽至 4.0s~5.0s**，底层套接字超时必须 >= 6.0s，杜绝误杀落地节点。
     - 探测前记录前置代理基线出口 IP，若经前置测试的节点出口与基线出口完全相同，立即判定为“前置穿透失败/泄露”并淘汰。
   - **异步并发与批次保护**：
     - 推荐每批 15~20 节点并发，整批等待上限 35s~45s；
     - 严格使用 `concurrent.futures.as_completed` 回收完成的任务，严禁顺序遍历阻塞；
     - 退出或超时清理时，严格执行“先终止内核进程（`proc.kill()`），再关闭线程池”的安全顺序，防止套接字阻塞导致进程假死。
   - **sing-box 1.10+ 原生内核兼容与 Schema 洗炼**：
     - 待测节点清洗：过滤不支持的协议（`xhttp`/`splithttp`、`anytls`、`mieru`、`shadowsocksr`）；清理私有运行时字段（`domain_resolver`、`tls_fragment`、`tls_tricks`）；将非标准指纹（如 `custom`）安全归一化为 `chrome`。
     - 配置导出清洗：自动剔除已废弃的 `experimental.statistics`，规范化 `dns.servers` 地址语法。
2. **打标与规范命名**：
   - 前置标识顺序：严格为 `[国旗] [❇️] [✨️] [Fast] [国家]_[编号]`。
     - `❇️`：AI 三大全通。
     - `✨️`：综合全通能力徽章（AI三大通过 + YouTube免登录实播通过 + 四站免盾）。
     - `Fast`：测速达标/高速节点。
   - 后置后缀组合：`_USAI`（美国且AI全通落地）、`_Lnd`（常规中转落地）、`_NF`（Netflix）、`_D+`（Disney+）。
   - 编号机制：沿用老节点编号，新节点自动从 1 补齐最小空号。
3. **模版一致性与双配置文件强制同步导出**：
   - 采用与本项目完全相同的 `template.yaml` 母版（包含 Fake-IP DNS、域名嗅探、防 DNS 泄露分流及 Geox 规则）。
   - **双份配置一键同步导出**：每次测试流水线结束导出时，**必须且默认同时生成两份标准配置文件**：
     1. **sing-box 格式文件**（`.json`）：保持标准独立出站结构，导出前执行 `sing-box check` 严格校验；
     2. **Clash/Mihomo 格式文件**（`.yaml`）：以内置 `template.yaml` 为母版，自动将节点与分类组装注入。
   - 自动组装标准策略组：`🛡️ Front前置`、`⚡ Fast自动选择`、`🌏️ 节点选择`、`🚀 自动选择`、`🔄 手动切换`、`✨️ 综合全通`、`🔀 AI 服务`、`🇺🇸 Google`、`✅ 解锁USAI`、`✅ 解锁 AI`、`🎬 国际流媒体`、`🎥 奈飞解锁`、`✨ 解锁Disney+`、`🔒️ 落地节点`。
   - 自动注入国际流媒体分流规则，对落地节点自动绑定合法前置跳板与 `dialer-proxy`。

## 常用 CLI 命令

所有脚本位于 `<skill>/scripts/` 目录下（`<skill>` 为当前技能根目录）：

```bash
# 1. 完整全量测试并导出配置（默认包含 IP、AI、流媒体、免盾、YouTube免登、断流检测与命名渲染）
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --report <报告.json>

# 2. 轻量快速测试（跳过浏览器免盾与 YouTube 实播，仅测 IP属地、AI接口、流媒体与连通性）
python <skill>/scripts/probe_services.py --input <输入源> --output <输出.yaml> --no-browser

# 3. 指定测试维度
python <skill>/scripts/probe_services.py --input <输入源> --tests ip,ai,media --output <输出.yaml>

# 4. Windows 本机与 TUN (如 Karing) 共存模式（绑定物理网卡，指定直连基线代理防污染）
python <skill>/scripts/probe_services.py --input <输入源> --iface WLAN --direct-proxy http://127.0.0.1:24999 --output <输出.yaml>

# 5. 指定自选母版模版渲染
python <skill>/scripts/probe_services.py --input <输入源> --template <自定义template.yaml> --output <输出.yaml>

# 6. sing-box 原生双轨全量服务测试与配置导出 (默认全量测试: IP、AI、YT免登、免盾、流媒体、测速，Schema清洗与导出)
python <skill>/scripts/probe_singbox.py --input <输入.json> --output <输出.json> --front-proxy 127.0.0.1:3067 --batch-size 20
```

## 按需查阅

- **测试判据与详细规范**：读 [testing-criteria.md](references/testing-criteria.md)。
- **运行环境、内核配置与 TUN 共存**：读 [runner-environment.md](references/runner-environment.md)。
- **策略组映射与 YAML 配置渲染**：读 [config-rendering.md](references/config-rendering.md)。
