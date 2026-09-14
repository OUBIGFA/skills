# 真实出口检测（仅在明确要求真实出口时触发）

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


检测授权不自动包含按结果改名或排序；写回仅在用户明确要求时进行。工作目录用任务 `_temp/<唯一目录>`。
