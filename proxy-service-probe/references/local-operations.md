# 本地整理

命令中的 `<skill>` 是本技能根目录；不启动网络探测。



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

- **重命名规范（仅在指定 `--rename` 时生效）**：`{国旗} {国家}[_{具体位置}]_{编号}[_{自定义后缀}]`。与 `--sort` 同用时先排好全部位置，再按 `国家[_位置]` 从 1 依次编号。
- **自定义标记 100% 完整保留（零硬编码）**：凡符合标准命名前缀的节点，编号后面的全部内容（如 `🟩`、`🔴`、`_USAI❇️`、`_base`、`-专线` 等）均被识别为用户手动标记完整保留，绝不硬编码关键词白名单，绝不将数字后依附的符号误判为城市。
- **地区排序顺位（仅在指定 `--sort` 时生效）**：港澳台 → 日韩新 → 东南亚/南亚 → 中东 → 北美 → 欧洲 → 大洋洲/南美 → 未知（`🏳️ 未知` 垫底）。

### 2. 多订阅合并 (`merge_configs.py`)

同时原生支持 **Clash YAML (.yaml/.yml)** 与 **sing-box JSON (.json)** 两种格式：

```bash
# 1. 默认合流模式（自动按指纹去重，优先保留底库原节点及原有编号，新节点补空号排位，地区聚拢）
python <skill>/scripts/merge_configs.py --base <底库.yaml> --add <新订阅.yaml> --apply

# 2. 中间插入模式（打破原编号壁垒，完全按能力顺位重排序，并从 1 重新依次连续编号）
python <skill>/scripts/merge_configs.py --base <底库.yaml> --add <新订阅.yaml> --insert --apply

# 3. 合并写入新文件（底库不动，自动生成备份）
python <skill>/scripts/merge_configs.py --base <底库.yaml> --add <新订阅.yaml> --out <新文件.yaml> --apply

# 4. 可选参数：--no-dedup（保留重复节点）
```

- **连接身份去重**：严格比对 `协议 + 服务器地址 + 端口 + 凭据(UUID/密码) + 传输方式 + 路径 + SNI + Reality Public Key`。
- **默认模式（优先保留原号）**：底库现有节点的名称与编号 100% 保持不动；新节点根据国家在底库已有编号的空缺位置（如 1, 2, 5 之间填入 3, 4）或末尾分配最小可用空号；最后按国家规范顺序排位，落地节点自动置于该地区最末尾。
- **中间插入模式（`--insert` / `--resort`）**：将底库节点与新节点全部打散，严格按照 `✨️ > ❇️ > Key > Fast > _NF > _D+ > 纯净优于污染 > ♥️ > 信誉分` 进行能力重排，落地沉底，位置完全确定后从 1 开始重新连续编号。

---
