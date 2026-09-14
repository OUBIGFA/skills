---
name: proxy-yaml-converter
description: 把 sing-box 节点转为 Clash/Mihomo 配置，或明确要求节点连通性测速时使用。
---

# sing-box 转 Clash/Mihomo

不是 JSON 到 YAML 的表面转换：提取真实代理节点，排除 direct/block/dns 和内部策略组，按目标协议字段构造非空 proxies 及相关分组规则。

- 本地格式转换：读 [conversion.md](references/conversion.md)，使用 `scripts/convert.py`。保留源顺序、完整协议字段与 AnyTLS 等节点；不支持的协议明确报告，不静默丢弃。重名加后缀并同步引用。
- 用户明确要求连通性、延迟测试或清洗时：才读 [speedtest.md](references/speedtest.md)，使用 `scripts/speedtest.py`；转换本身不授权启动内核或全节点联网测速。

默认保留脚本提供的节点选择/自动选择分组与分流规则，并说明其中自动测速在客户端启用配置后可能联网。输出使用无 BOM UTF-8，检查节点数、字段、分组和规则引用。覆盖已有文件前保留备份，不自动清洗或按延迟重排。
