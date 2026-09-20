---
name: proxy-service-probe
description: 对代理节点执行服务能力测试（IP属地检测、AI解锁、YouTube免登实播、免盾过盾、流媒体、打标命名及Clash/Mihomo配置渲染）时使用。
---

# 代理节点服务能力测试与配置渲染 (proxy-service-probe)

对代理节点（Clash YAML、sing-box JSON、节点订阅链接或 URI）执行全方位的服务能力检测、智能淘汰断流与失效节点、生成规范化角色与能力标签，并依据项目级 `template.yaml` 渲染导出完整的 Clash/Mihomo 订阅配置文件。

## 核心契约

1. **测试范围与判定依据**：
   - **IP 属地与出口**：双栈真实出口探测；Google 自身地区码判定（Gemini 页面内嵌 ISO 地区码优先，YouTube Premium 兜底）；多源 GeoIP 投票（ipwhois、ip.sb、Net.Coffee）；Net.Coffee 欺诈信誉分与网络属性（机房/家宽/代理/爬虫）；送中（Google Mainland CN）拦截标记。
   - **AI 解锁**：ChatGPT/OpenAI（合规端点 200 + 移动端/模型端点连通）、Claude（模型端点 401 判通）、Gemini（页面可用性标志 `[45631641,null,true]` 实测）；三项通过且出口稳定非送中标记为“AI三大全通”。
   - **YouTube 免登录实播**：Playwright Chromium 真实无头环境，注入 HTML5 播放观察者（实播 >= 10 秒、非缓冲停滞、非人机验证 / bot_required），播放前后双向复核浏览器出口 IP，通过 2 个视频判定免登实播达标。
   - **过盾 / 免盾**：HTTP 初查 + 浏览器针对 4 站（Cloudflare 官网、ChatGPT、Claude、Gemini）的质询检测，4 站观测齐全且至多 1 站遇到挑战（且自动解除）判定为免盾。
   - **流媒体与带宽**：Netflix（非自制剧 200）、Disney+ 页面可用性；3 秒流式下载窗口带宽测试，3 秒不足 300KB 标记为“断流假死”淘汰。
   - **前置跳板与落地链式测试**：支持直连节点直接测试；支持落地节点（HTTP/Socks5/landing标记）通过前置跳板（Dialer-Proxy）建立链式隧道后再进行全套服务测试。
2. **打标与规范命名**：
   - 前置标识顺序：严格为 `[国旗] [❇️] [✨️] [Key/Fast] [国家]_[编号]`。
     - `❇️`：AI 三大全通。
     - `✨️`：综合全通能力徽章（AI三大通过 + YouTube免登录实播通过 + 四站免盾）。
     - `Key`：大陆探针实测高分优质直连跳板前置。
     - `Fast`：测速达标/高速节点。
   - 后置后缀组合：`_USAI`（美国且AI全通落地）、`_Lnd`（常规中转落地）、`_NF`（Netflix）、`_D+`（Disney+）。
   - 编号机制：沿用老节点编号，新节点自动从 1 补齐最小空号。
3. **模版一致性与配置渲染**：
   - 采用与本项目完全相同的 `template.yaml` 母版（包含 Fake-IP DNS、域名嗅探、防 DNS 泄露分流及 Geox 规则）。
   - 自动组装标准策略组：`🛡️ Front前置`、`⚡ Fast自动选择`、`🌏️ 节点选择`、`🚀 自动选择`、`🔄 手动切换`、`🔀 AI 服务`、`🇺🇸 Google`、`✅ 解锁USAI`、`✅ 解锁 AI`、`🎬 国际流媒体`、`🎥 奈飞解锁`、`✨ 解锁Disney+`、`🔒️ 落地节点`。
   - 自动注入国际流媒体分流规则，对落地节点自动绑定合法前置跳板。

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
```

## 按需查阅

- **测试判据与详细规范**：读 [testing-criteria.md](references/testing-criteria.md)。
- **运行环境、内核配置与 TUN 共存**：读 [runner-environment.md](references/runner-environment.md)。
- **策略组映射与 YAML 配置渲染**：读 [config-rendering.md](references/config-rendering.md)。
