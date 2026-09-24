# IP 属地证据链与复核（2026-09-23 升级）

## 范围

`core/egress_geo.py` 是 `probe_services.py`、`probe_singbox.py` 和 `audit_geolocation.py` 的共享控制点。本次升级不改订阅、不测速，不以旧节点国旗、服务器入口 IP、ASN 注册国或 CDN 接入机房作为属地真值。

## 开源参考与活跃度核验

2026-09-23 通过 GitHub 仓库元数据核对，另读下列实际实现；只参考数据接口和判据，没有执行上游脚本，也没有移植整段上游代码。

| 项目 | 核验时状态 | 采用的思路 / 边界 |
|---|---|---|
| [xykt/IPQuality](https://github.com/xykt/IPQuality) | 10,459 stars；最近 push 2026-09-16；AGPL-3.0；未归档 | `ip.sh` 将 IPinfo 的地理国家 `.data.country` 与注册国家 `.data.abuse.country` 分开展示，并查询多家数据源。借鉴这种口径分离，不把注册地等同于属地。 |
| [jason5ng32/MyIP](https://github.com/jason5ng32/MyIP) | 11,938 stars；最近 push 2026-09-22；MIT；未归档 | `api/ipapi-is.js`、`api/ipinfo-io.js` 对不同 schema 做显式标准化，并处理 HTTP 200 但缺 location / ASN 的响应。新增 ipapi.is 适配和空字段校验。 |
| [lmc999/RegionRestrictionCheck](https://github.com/lmc999/RegionRestrictionCheck) | 5,135 stars；最近 push 2025-12-08 | 调研对照，不把较久未更新的服务正则直接当当前有效契约。 |

这些是开源探测项目，不代表其使用的商业 GeoIP 数据库也开源，更不代表多个库拥有完全独立的数据血缘。Google 正则还用当日真实 Gemini / YouTube 响应验证；页面结构改变时保留未知，不强行回填。

## 判定顺序

1. **真实出口**：CF trace 与独立 HTTPS 回显交叉采样；IPv4/IPv6 使用 `ipaddress` 校验，按地址族单列。地理检测前后再核对出口。
2. **Google 地区**：仅采纳 Gemini 明确的唯一 ISO alpha-3；YT 须两个唯一国家标记一致才兜底。`google.com`、`hl=en` 等不计票。遇缺失、Google 子服务分歧或 GeoIP 强分歧时复查一次；地区变化撤销 Google 定国资格，不无限重试。
3. **IP 数据库**：逐个真实出口查 IPinfo、ipwho.is、ipapi.is、DB-IP。返回的 IP 必须等于请求目标；丢失、私网、错误、限流、非 JSON 均不计票。ipapi.is 兼容免费扁平 schema 与嵌套 location schema。
4. **共识**：同来源族仅一票；至少两票且严格过半。平票和单票不确证。CF `loc` 是辅助来源，`colo` 无论多近都不计票。取消“离岸国家黑名单”，避免误伤真实塞舌尔/塞浦路斯等出口。
5. **现有送中方案优先**：数据库确定韩国、Gemini 为中国，保留 `KR`，标 `is_poisoned` / `_⚠️CN` 并剥离 `❇️`、`✨️`。这不是普通未知属地，也不能将国旗改成中国。受限地区污染沿用同类标记；任一次可信送中观测不能被非 CN 多数票清除。
6. **其余冲突**：普通非受限 Google 国家与数据库强共识冲突时，保留候选和全部口径、国别暂为 `UNK`。仅部分数据库分歧时保留候选但降置信度。Google 地区无效时才按 GeoIP/CF 共识定国，不用旧名称兜底。
7. **多出口**：同族多个 IP 才是疑似轮换池，IPv4+IPv6 本身不是。跨出口国家冲突或复核失败不可报告稳定。Google 请求无法直接回显源 IP，报告不能声称已证明其目的站出口与回显站完全相同。

## 可追溯报告

- `google_region`：来源、显式国家码、可用标记、送中标志、初次/重复观测。
- `ip_info_by_ip`：每个实际 IP 的国家共识、逐来源响应状态、目标 IP、回显 IP。
- `geo_decision`：`cc`、`candidate_cc`、`scope`、`basis`、置信度、待复核、出口稳定性与污染标记。
- 每次请求留 URL、UTC 时间、HTTP 状态、正文 SHA-256；失败留错误类型。Net.Coffee 不计属地票，仅在 IP 绑定校验成功时保留信誉。
- 主流程的 JSON 报告保留上述字段，不再只保存最后一个国家码。不要复用升级前的检查点作为新规则的验证结果。

## 纯属地抽查

```bash
python <skill>/scripts/audit_geolocation.py \
  --input <配置.yaml> --report <新目录/复核.json> \
  --count 20 --seed 20260923 --workers 2 --batch-size 5 \
  --mihomo <mihomo.exe> --iface WLAN \
  --include "🇸🇬 ❇️新加坡_4"
```

- 可重复 `--include` 指定必选节点。其余按原国旗分层、固定 seed 抽样；原名只参与抽样。
- 临时监听绑定 `127.0.0.1`，动态端口，不修改 Windows 代理/路由/TUN。直连基线也通过绑定物理网卡的隔离内核 DIRECT 出站获取。
- 链式节点默认排除，避免拆掉 `dialer-proxy` 后假装复核了原拓扑。直连不可达只代表本次隔离直连路径失败，不能推断用户客户端经前置也不可用。
- **ip.cx 是留出来源，不参与自动仲裁**。另一次无 Cookie Gemini 请求做时间复核。ip.cx 网络超时最多追加一次请求并保留首次失败，不绕过挑战页。
- 生成同名 JSON、Markdown 和 `.evidence/` ip.cx 原页。既有报告不覆盖；输入文件 SHA-256 检测前后保持一致。
- `verified` 是来源一致，不是地理真值认证；`verified_sent_to_china` 表示实际属地和送中分别复核成功；`verified_correction` 表示出口 IP 未变化，ip.cx 与第二次 Gemini 共同确认了不同于自动判定的国家，报告中的 `recommended_cc` 才是可供人工确认的修正候选。离线、证据不足、轮换和分歧分别统计，不算通过。
- 抽查不要将预筛后的样本一致率宣传为全订阅准确率。需要补抽时保留首轮完整失败记录，并说明补抽口径。

## 验证

```bash
python -B -m unittest discover -s <skill>/tests -v
```

测试覆盖 Google 默认美国误票、Gemini/YT 缺失与分歧、重复请求上限、送中保留韩国并剥离徽章、来源 IP 错配、平票/单票/同源去重、IPv6、出口轮换和两条主流水线报告接入。旧 `probe.py` / `recheck.py` / `verdict.py` 是历史测绘流程，未迁移到这条证据链；新属地任务应使用上述入口，不混用其旧结果冒充本次升级报告。
