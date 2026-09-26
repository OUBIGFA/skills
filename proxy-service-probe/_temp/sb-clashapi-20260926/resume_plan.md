# sing-box 流水线续测（2026-09-26）

输入：D:\Data\Desktop\_scratch\test.json（只读；初始 SHA256：3ECD167EFEF58099C8D6F328DD5533AFFEA2D59B3E4C2D512B13194446388049）

- [x] 恢复现场；无运行中的测试；166 项 unittest 通过（HTTPServer ResourceWarning 待修正）。
- [x] 同物理网卡下对照真实 sing-box / Mihomo 全量测活：12 个均加载，3 个直连通，两内核一致（resume_kernel_compare.json）。
- [x] 全量 sing-box 服务（含完整 Chromium）+ 持续测速：resume_run2 / resume_run3，均真实完整运行，不降级、不放宽门槛。run3 为 4/12、Key 1、落地 1，145.7 秒。
- [x] 修复并补回归：动态落地禁止 Key、淘汰前置不得留下未验证落地、等待前置空闲重测与出口证据、错误任务不能假成功、中国排序、报告保留服务证据；浏览器缺出口不通过、广告/缓冲/跳进度不算实播。193 项测试通过（resume_unit2.log）。
- [x] 同步双线流程、前置回退、物理中继及报告文档；旧 --front-proxy 兜底已移除说明。
- [ ] 最终双内核配置校验、输出拓扑及进程清理；交付配置、报告与未通过原因。run3 JSON check=0；YAML 尚因空数据目录下载 GeoSite 失败（DNS 引导问题），并发现母版过时的全局指纹选项已删除，待重渲染复验。
- [ ] 对法国 YouTube 的 readyState=4 但 played=0 做定向诊断，确认是否广告或同意页消耗观察窗，不放宽实播证据。

边界：保护已有改动；不改系统代理、路由与 TUN；只用临时环回监听。当前 sing-box 1.14.1 / Mihomo 1.19.31 / Python 3.11.9，物理网卡 WLAN。