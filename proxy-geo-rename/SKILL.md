---
name: proxy-geo-rename
description: 代理配置文件（sing-box JSON）节点统一重命名、按地区排序、合并订阅去重与真实出口测绘。默认采用快速本地模式（sort_nodes.py / merge_configs.py）：按【国旗 地区_具体位置_编号_自定义后缀】格式快速规范化重命名、按使用习惯地区排序、连接身份去重并完整保留自定义后缀（如 USAI、AI、❇️、USAI❇️、AI❇️、China、家宽、base 等），毫秒级完成且无需网络探测；仅在用户明确要求“检测真实出口/真实落地/多源测绘/查伪装地区”时，才调用本机 sing-box 内核进行多源出口测绘与投票仲裁流程。
---

# proxy-geo-rename：代理节点统一重命名、地区排序与出口检测

## 模式选择（默认轻量快速）

本技能包含两种工作模式，**默认使用模式 A**：

| 模式 | 适用场景 | 执行方式 | 耗时与开销 |
|---|---|---|---|
| **模式 A：快速整理（默认）** | 用户要求重命名、整理节点名、按地区排序、合并去重、分类转移节点、保留自定义后缀等常规任务 | 本地解析现有节点名与配置信息，直接格式化重排 | **毫秒级**，零网络流量，无需启动内核 |
| **模式 B：深度出口测绘（仅明确要求时触发）** | 用户明确要求“检测真实出口”、“测落地 IP”、“多源测绘”、“查是否伪装地区”、“网络探测” | 启动本机已有 sing-box 内核，通过每个节点向 8 个独立地理库查询出口并投票裁决 | 2~5 分钟，需内核及物理网卡绑定 |

> [!IMPORTANT]
> **默认行为准则**：除非用户在 Prompt 中明确包含“真实出口”、“检测落地”、“多源测绘”、“查真实归属”、“测伪装”等字眼，否则**一律走模式 A（快速整理）**，切勿擅自启动 sing-box 内核或发起网络探测。

---

## 模式 A：快速重命名、地区排序与合并去重（默认模式）

脚本位于本 skill 的 `scripts/` 目录。

### 1. 单配置重命名与地区排序

```bash
# 预览重排结果（dry-run）
python <skill>/scripts/sort_nodes.py --config <配置.json>

# 确认无误后写回（写回前自动创建时间戳备份）
python <skill>/scripts/sort_nodes.py --config <配置.json> --apply
```

- **命名规范**：`{国旗} {国家}[_{具体位置}]_{编号}[_{自定义后缀}]`（如 `🇯🇵 日本_东京_1`、`🇺🇸 美国_1_China`、`🇺🇸 美国_洛杉矶_2_USAI❇️`、`🇺🇸 美国_3_USAI`、`🇯🇵 日本_2_AI`、`🇭🇰 香港_1_❇️`）。
- **内置地名识别**：已内置包含全球主要枢纽（巴黎、伦敦、法兰克福、阿姆斯特丹、首尔、东京、洛杉矶、台北、桃园等 40+ 城市及 IATA 机场代码）与拼音/中文城市识别；港澳新等城邦自动精简不重复（如 `🇭🇰 香港_1`、`🇸🇬 新加坡_1`）。
- **自定义标记保留**：自动提取并保留 `USAI`、`AI`、`❇️`、`USAI❇️`、`AI❇️`、`China`、`家宽`、`魔改`、`实验性`、`base` 等自定义标记。
- **地区排序**：港澳台 → 日韩新 → 东南亚/南亚 → 中东 → 北美 → 欧洲 → 大洋洲/南美 → 未知（`🏳️ 未知` 垫底），同地区编号连续。

### 2. 多个订阅合并与去重

```bash
# 预览合并去重效果
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> <订阅2.json>

# 实际合并写入底库（自动备份底库、去重、并入新节点后自动执行统一命名与地区排序）
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> <订阅2.json> --apply

# 保持底库不动，合并结果另存为新文件
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> --out <新文件.json> --apply
```

- **连接身份去重**：严格比对 `协议 + 服务器地址 + 端口 + 凭据(UUID/密码) + 传输方式 + 路径 + SNI`，只有连接信息完全一致才视为重复，避免误删同机不同配置。
- **引用清洗**：自动清洗源配置中的私有 `domain_resolver` 和悬空 `detour`，合并后自动同步更新各 `urltest`/`selector` 分组成员。

---

## 模式 B：真实出口地理检测与多源投票（仅明确要求时使用）

当用户明确需要**检测真实出口归属或验证节点是否伪装地区**时使用此流程。

### 步骤 0：环境准备与物理网卡确认
1. 查找本机已有的 `sing-box.exe`（禁止未经允许擅自下载新可执行程序）。
2. 查 TUN 网卡接管：`Get-NetAdapter | Where-Object Status -eq Up`，若有 TUN 虚拟网卡，必须获取物理网卡名（如 `WLAN`、`以太网`）并传入 `--iface`。

### 步骤 1：主检测与复核
```bash
# 1. 测出口地理位置（5个主地理源 + Cloudflare 机房物理决胜）
python <skill>/scripts/probe.py --config <配置.json> --singbox <内核路径> --iface <物理网卡> --workdir <workdir>

# 2. 二次复核（离线重试、中转复活探测、增补 3 个地理库重投票）
python <skill>/scripts/recheck.py --workdir <workdir>
```

### 步骤 2：存疑节点延迟仲裁（可选）
对于数据库分歧、多库投票分散的中低置信节点：
```bash
python <skill>/scripts/latency_arbiter.py --workdir <workdir>
# 将终裁写入 <workdir>/overrides.json
```

### 步骤 3：重命名写回
```bash
# 预览
python <skill>/scripts/rename.py --workdir <workdir>
# 确认后写回
python <skill>/scripts/rename.py --workdir <workdir> --apply
```

---

## 模式与常用指令速查

| 用户意图 | 推荐脚本与指令 |
|---|---|
| “帮我重命名 / 整理这个订阅里的节点” | `python sort_nodes.py --config <配置.json> --apply` |
| “把多个订阅合并在一起并去重” | `python merge_configs.py --base <底库.json> --add <新配置.json> --apply` |
| “把特定后缀（如 USAI❇️）的节点转移走” | 本地 Python 筛选对应 tag 节点并入目标文件，随后分别对两文件执行 `sort_nodes.py --apply` |
| “检测节点的真实落地 IP / 判断是否伪装” | `python probe.py ...` → `recheck.py` → `rename.py --apply` |
| “将运行时快照配置转成客户端可导入的轻量 profile” | `python make_profile.py --config <配置.json>` |
