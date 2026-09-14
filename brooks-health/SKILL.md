---
name: brooks-health
description: 用户要求代码质量综合评估，涵盖架构、维护成本和测试时使用。
---

# brooks-health

先确定用户请求的范围与模式，不因架构、重构或健康等单词自行扩大任务。除 brooks-sweep 或明确授权修复外，只读分析，不自动修改历史记录或项目配置。

## 按需加载

- 本模式的方法：[health-guide.md](health-guide.md)。

- 存在 `.brooks-lint.yaml` 或需要确定范围、报告与评分规则时，读取 [common.md](../_shared/common.md) 的相关部分；不存在配置则沿用默认风险分类。
- 生产代码、架构或技术债的具体风险分类：按问题读取 [decay-risks.md](../_shared/decay-risks.md)。
- 现有测试质量的具体风险分类：按问题读取 [test-decay-risks.md](../_shared/test-decay-risks.md)。
- 需要书籍归因、例外或权衡依据时才读 [source-coverage.md](../_shared/source-coverage.md)，不要给未经核实的来源背书。

## 结果与权限

发现需给出实际位置、现象、来源或依据、后果与可行修复，不凑发现数量。说明实际检查范围和证据缺口；分数是启发式评估，不是质量保证。

已授权的本地修复可连续实施、验证、修复失败并复验。高影响范围变化仍需相应授权；资源上限或无进展时报告真实剩余问题，不能视为全部修复。只读审计不因参考文档要求写历史而改变范围。
