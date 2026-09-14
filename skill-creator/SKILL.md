---
name: skill-creator
description: 创建、修改技能，或检验技能触发是否准确时使用。
official: true
version: 1.0.1
---

# 技能创建与优化

技能只补充非显而易见且影响结果的知识，不重复模型已有常识。保留用户意图、任务范围、明确权限和具体数据契约。

## 编写原则

- 描述简短，写清实际请求与边界；不罗列宽泛关键词，不用“1% 可能”或 pushy 扩大触发。
- 根文件保留用途、关键边界和按任务分支读取的路由。复杂方法、接口、示例和评估放参考资料；简单技能不用硬拆。
- 复用现有脚本和资源，不整篇复制教程；移动文档时同步相对路径和调用方。
- 保留现有发现策略和元数据，除非用户明确要求改变。避免同名入口同时暴露；默认不自动安装、发布、推送或调用子代理。
- 普通修改做相称验证；可批量处理后统一校验，不要求每次编辑先跑失败实验。

## 按需资料

- 接口元数据：改 `agents/openai.yaml` 时读 [openai_yaml.md](references/openai_yaml.md)。
- 触发正反例、版本对照、可选 Claude CLI 评估：读 [evaluation.md](references/evaluation.md)。
- 需要评估文件结构：读 [schemas.md](references/schemas.md)。
- 只有正式委派评估时才读取 `agents/grader.md`、`agents/comparator.md` 或 `agents/analyzer.md`。

## 验收

检查 YAML、名称、描述、引用和脚本路径；有新脚本时在代表性输入上运行。用相邻任务正反例核对触发边界；静态判断不是模型实测触发率。修复发现的问题并复验，不以生成文件成功代替完成。
