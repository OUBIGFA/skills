---
name: subagent-driven-development
description: 用户允许子代理后，执行可独立拆分的实施计划时使用。
---

# 授权后的协作实施

仅在用户已允许子代理时使用；单代理任务不因此改变执行方式。

- 按实施计划与文件所有权分工，使用当前宿主真实工具，不固定代理数量或模型。
- 过程材料放 `_temp/<任务>/`；保护已有工作区和未提交改动。
- 派发实现时按需读 [implementer-prompt.md](implementer-prompt.md)；确需独立审查时读 [task-reviewer-prompt.md](task-reviewer-prompt.md)；复审只读 [re-review-prompt.md](re-review-prompt.md)。
- 主代理可以直接修复，也可以继续委派；对审查意见以需求和证据裁定，不固定多轮审查。
- 汇总后检查差异与实际行为，修复并复验。轮数或预算耗尽时标明未完成和阻碍，不能把真实问题改称已完成。
- 只清理本次创建的材料并送入回收站；提交、推送、合并和发布按已有明确授权执行。
