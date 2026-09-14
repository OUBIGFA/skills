---
name: proxy-geo-rename
description: 整理 sing-box 节点的去重、命名或顺序，或明确要求检测真实出口时使用。
---

# sing-box 本地整理与真实出口检测

## 核心契约


1. 合并、追加、导入或整理默认按完整连接身份指纹去重，并移除代理节点的 `detour`；可用 `--keep-dup`、`--keep-detour` 保留。指纹覆盖协议、地址、端口、凭据、传输、路径、SNI 等实际连接字段，不含 Tag。
2. 只有用户明确要求时才排序或重命名；未要求时保留节点名称和顺序。
3. 只有用户明确要求真实出口、落地 IP、多源测绘或查伪装时，才启动 sing-box 和网络探测。
4. `--apply` 写回前自动备份；内容无变化时不写回、不生成备份。写回后校验全部 Tag、分组成员、`default`、`detour`、`route.final`、路由规则和 DNS 引用。


## 按需读取

- 单文件整理、合并、重命名或排序：[local-operations.md](references/local-operations.md)。使用 `scripts/sort_nodes.py` / `scripts/merge_configs.py`；Profile 提取使用 `scripts/make_profile.py`。
- 只有明确要求真实出口检测时才读 [egress-probing.md](references/egress-probing.md)，启动 sing-box 与网络探测；检测本身不授权改名或排序。
- 检测失败或环境异常才读 [troubleshooting.md](references/troubleshooting.md)。

本地整理只需 Python 3.9+；检测另需已有 sing-box 与 requests。保留用户标记、连接身份、引用一致性及写前备份；不把 TUN 污染的结果当成已确认真实出口。
