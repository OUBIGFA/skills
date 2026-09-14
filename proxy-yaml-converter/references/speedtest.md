# 明确请求的测速与清洗



在选定**前置节点**或定期巡检代理配置时，必须获取真实的连通情况。如果系统启用了 TUN 模式或系统代理，普通测速请求会被现有代理劫持，导致假活（看似通畅实际直连已死）。

`speedtest.py` 核心特性：
1. **物理网卡绑定**：检测活跃物理网卡并设置 `interface-name`，以减少 TUN/系统代理污染；仍需检查实际绑定及结果，不能无条件保证完全绕过。
2. **内核自动发现**：自动定位本地已安装的 Mihomo / Clash Party / Clash Verge / Mihomo Party 内核。
3. **隔离临时沙箱**：启动独立的临时进程与动态随机端口，测试结束后彻底清理释放，不影响后台主客户端运行。
4. **并发与重试**：支持并发测速及有界重试；并发量以网络和内核承受能力为准。
5. **原地清洗与分组同步**：使用 `--filter-alive` 时自动剔除死节点，并同步更新 `proxies` 和 `proxy-groups` 内的引用。

#### 常用命令

```bash
# 1. 对指定 YAML 进行直连测速并显示报告（不修改原文件）
python E:/_BIGFAFree/_code/skills/proxy-yaml-converter/scripts/speedtest.py -i D:/Data/Desktop/qianzhi.yaml

# 2. 直连测速并直接原地移除不通节点（更新 proxies 和所有代理组）
python E:/_BIGFAFree/_code/skills/proxy-yaml-converter/scripts/speedtest.py -i D:/Data/Desktop/qianzhi.yaml --filter-alive

# 3. 原地移除死节点，并将可用节点按延迟从低到高重新排序
python E:/_BIGFAFree/_code/skills/proxy-yaml-converter/scripts/speedtest.py -i D:/Data/Desktop/qianzhi.yaml --filter-alive --sort

# 4. 测速后保存为新文件，保留原文件不动
python E:/_BIGFAFree/_code/skills/proxy-yaml-converter/scripts/speedtest.py -i in.yaml -o out_alive.yaml --filter-alive --sort

# 5. 指定网络接口、并发数与超时阈值
python E:/_BIGFAFree/_code/skills/proxy-yaml-converter/scripts/speedtest.py -i config.yaml --interface "WLAN" --timeout 3000 --workers 20 --filter-alive
```

---



以真实绑定与测试结果确认直连，不能仅凭脚本声称绕过 TUN 就保证成功。清洗、排序和原地写回需分别符合用户请求；覆盖前保留备份。中间配置放任务 `_temp/<唯一目录>`，只结束本次启动的测试进程。
