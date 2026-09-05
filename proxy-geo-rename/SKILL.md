---
name: proxy-geo-rename
description: Use when handling sing-box JSON proxy configurations that need connection-fingerprint deduplication, detour removal, on-demand node renaming or regional sorting, or explicitly requested real-egress probing.
---
# proxy-geo-rename：代理节点重命名、排序、合并去重与出口检测

## 核心行为准则

1. 合并、追加、导入或整理默认按完整连接身份指纹去重，并移除代理节点的 `detour`；可用 `--keep-dup`、`--keep-detour` 保留。指纹覆盖协议、地址、端口、凭据、传输、路径、SNI 等实际连接字段，不含 Tag。
2. 只有用户明确要求时才排序或重命名；未要求时保留节点名称和顺序。
3. 只有用户明确要求真实出口、落地 IP、多源测绘或查伪装时，才启动 sing-box 和网络探测。
4. `--apply` 写回前自动备份；内容无变化时不写回、不生成备份。写回后校验全部 Tag、分组成员、`default`、`detour`、`route.final`、路由规则和 DNS 引用。

## 环境与依赖

- 本地整理和 Profile 提取只需要 Python 3.9+，不依赖 `requests`。
- 出口测绘还需要用户已有的 `sing-box` 可执行文件和 `requests`；Windows 下检查 TUN 时使用 PowerShell。
- 深度测绘遇到网络、DNS、内核版本或前置代理问题，先读 [references/troubleshooting.md](references/troubleshooting.md)。

---

## 常用指令与用户意图速查

| 用户意图 | 推荐脚本与参数 | 行为保障 |
|---|---|---|
| **“帮我合并这几个订阅”** | `python merge_configs.py --base <底库.json> --add <订阅1.json> ... --apply` | **合并**：自动去重、自动剥离 detour；**不改名、不调序** |
| **“合并并按地区排序”** | `python merge_configs.py --base <底库.json> --add <订阅1.json> ... --sort --apply` | 自动去重+剥离 detour，按地区排序，**不改名** |
| **“合并并规范重命名”** | `python merge_configs.py --base <底库.json> --add <订阅1.json> ... --rename --apply` | 自动去重+剥离 detour，规范改名，**保持原有前后顺序** |
| **“合并、排序并规范重命名”** | `python merge_configs.py --base <底库.json> --add <订阅1.json> ... --sort --rename --apply` | 执行完整合并整理流水线 |
| **“只帮我把节点按地区排下序”** | `python sort_nodes.py --config <配置.json> --sort --apply` | 自动去重+剥离 detour，**仅排序，节点名称 100% 原样保留** |
| **“只帮我规范化重命名节点”** | `python sort_nodes.py --config <配置.json> --rename --apply` | 自动去重+剥离 detour，**仅改名，原有先后顺序 100% 保持原样** |
| **“帮我把节点重命名并排序”** | `python sort_nodes.py --config <配置.json> --sort --rename --apply` | 排序并规范化重命名（含自动去重与剥离 detour） |
| **“帮我把配置去重并去掉链式代理”** | `python sort_nodes.py --config <配置.json> --apply` | 自动去重与剥离 detour，**不改名、不调序** |
| **“检测真实出口 / 测落地 IP / 查伪装”** | `python probe.py ...` → `recheck.py` → `rename.py --apply` | 启动内核真实出口多源投票（自动剥离 detour，默认不排序除非加 `--sort`） |
| **“提取干净的可导入轻量 profile”** | `python make_profile.py --config <配置.json>` | 去重并剥离客户端运行时 dump、`detour` 和私有 DNS 引用 |

---

## 本地快速处理模块

脚本位于本 skill 的 `scripts/` 目录。

### 1. 节点排序与重命名 (`sort_nodes.py`)

严格按用户指令决定是否排序或重命名：

```bash
# 仅按地区排序（名称 100% 原样保留，默认自动去重与剥离 detour）
python <skill>/scripts/sort_nodes.py --config <配置.json> --sort --apply

# 仅规范化重命名（顺序 100% 原样保留，默认自动去重与剥离 detour）
python <skill>/scripts/sort_nodes.py --config <配置.json> --rename --apply

# 排序 + 规范化重命名（用户同时要求时）
python <skill>/scripts/sort_nodes.py --config <配置.json> --sort --rename --apply

# 仅单文件去重与剥离 detour（不改名、不调序）
python <skill>/scripts/sort_nodes.py --config <配置.json> --apply

# 可选保留参数：--keep-dup（保留重复节点）、--keep-detour（保留链式代理）
```

- **重命名规范（仅在指定 `--rename` 时生效）**：`{国旗} {国家}[_{具体位置}]_{编号}[_{自定义后缀}]`。
- **自定义标记 100% 完整保留（零硬编码）**：凡符合标准命名前缀的节点，编号后面的全部内容（如 `🟩`、`🔴`、`_USAI❇️`、`_base`、`-专线` 等）均被识别为用户手动标记完整保留，绝不硬编码关键词白名单，绝不将数字后依附的符号误判为城市。
- **地区排序顺位（仅在指定 `--sort` 时生效）**：港澳台 → 日韩新 → 东南亚/南亚 → 中东 → 北美 → 欧洲 → 大洋洲/南美 → 未知（`🏳️ 未知` 垫底）。

### 2. 多订阅合并 (`merge_configs.py`)

```bash
# 1. 基础合并（默认自动去重、自动剥离 detour，不改名、不调序）
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> <订阅2.json> --apply

# 2. 合并并按地区排序（名称原样保留）
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> --sort --apply

# 3. 合并写入新文件（底库不动）
python <skill>/scripts/merge_configs.py --base <底库.json> --add <订阅1.json> --out <新文件.json> --apply

# 4. 可选开关：--sort、--rename、--keep-dup（保留重复）、--keep-detour（保留链式）
```

- **连接身份去重**：严格比对 `协议 + 服务器地址 + 端口 + 凭据(UUID/密码) + 传输方式 + 路径 + SNI`。
- **重名保护**：未开启重命名时，若遇到同名 Tag，自动追加 `#2`、`#3` 编号，绝不误改其他节点名，确保配置合法性。

---

## 深度出口测绘模块（仅在明确要求真实出口时触发）

仅当用户明确出现“检测真实出口”、“测落地 IP”、“多源测绘”、“查伪装”时触发。

### 流程步骤
1. **环境与物理网卡确认**：查 TUN 网卡接管 `Get-NetAdapter | Where-Object Status -eq Up`，若有 TUN 虚拟网卡，获取物理网卡名（如 `WLAN`、`以太网`）传入 `--iface`。
2. **主测与复核**：
   ```bash
   python <skill>/scripts/probe.py --config <配置.json> --singbox <内核路径> --iface <物理网卡> --workdir <workdir>
   python <skill>/scripts/recheck.py --workdir <workdir>
   ```
3. **延迟仲裁（可选）**：
   ```bash
   python <skill>/scripts/latency_arbiter.py --workdir <workdir>
   ```
4. **按需写回**：
   ```bash
   # 仅按测绘结果重命名（保持原有顺序，自动剥离 detour）
   python <skill>/scripts/rename.py --workdir <workdir> --apply
   # 若用户同时要求排序，加 --sort
   python <skill>/scripts/rename.py --workdir <workdir> --sort --apply
   ```

`overrides.json` 使用如下格式，键可以是检测时或当前节点名：

```json
{
  "原节点名": {
    "cc": "DE",
    "country_zh": "德国",
    "city_zh": "法兰克福",
    "note": "物理测距终裁"
  }
}
```
