---
name: systematic-debugging
description: 故障原因不明、问题跨组件或修复后反复出现时使用。
---

# 根因调查

适用于原因不明、跨组件或反复出现的故障。明显的局部修复遵循 code-rules 即可。

1. 收集实际错误、输入、环境与近期变更，建立最小复现；无法复现时明确证据缺口。
2. 比较正常与异常路径，定位最早出现偏差的边界，再形成可检验假设。
3. 一次验证一个关键假设，观察结果；失败后更新假设，不叠加无依据修补。
4. 在根因所属位置修复，补充适当回归检查，再验证受影响流程。

重复失败是重新检查证据、假设或设计的信号，不是第三次自动停工。只有缺少权限、外部依赖、无法判断的重大取舍或持续无进展时如实说明阻碍；继续独立可完成的工作。

- 调用链追踪：[root-cause-tracing.md](root-cause-tracing.md)。
- 异步竞态与轮询：[condition-based-waiting.md](condition-based-waiting.md)。
- 确需多层防护：[defense-in-depth.md](defense-in-depth.md)，不为所有故障增加防护层。
