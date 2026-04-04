---
name: handoff-writer
description: |
  Write a handoff markdown file for the next AI agent so work can continue in a new session with minimal context loss.

  Triggers when user mentions:
  - "handoff"
  - "交接"
  - "交接文件"
  - "交接文档"
  - "交接摘要"
  - "对接"
  - "next agent"
  - "接手"
---

Create a handoff file at `./{yymmdd}-handoff.md` for the next AI agent.

Use the local current date for `{yymmdd}`. Write the document for another agent, not for the end user.

## Output rules

- Write the file to the current working directory unless the user gives a different path.
- Keep the content concrete, specific, and continuation-oriented.
- Prefer exact file paths, module names, commands, errors, decisions, assumptions, and constraints.
- Do not pad with pleasantries or generic summaries.
- Do not speculate. If something is unknown, say it is unknown or unverified.
- Preserve the most actionable context first: what is done, what remains, what to verify next.

## Required document structure

Use exactly this section order and headings:

```markdown
## 1. 当前任务目标
说明当前要解决的问题、预期产出和完成标准。

## 2. 当前进展
说明目前已经完成了哪些分析、确认、修改、排查、讨论或产出。

## 3. 关键上下文
包括但不限于：
- 重要背景信息
- 用户的明确要求
- 已知约束
- 已做出的关键决定
- 重要假设

## 4. 关键发现
列出目前最重要的结论、规律、异常点、根因判断、设计判断或值得注意的信息。

## 5. 未完成事项
列出仍需要继续处理的内容，并按优先级排序。

## 6. 建议接手路径
告诉下一位 Agent：
- 应优先查看哪些文件、模块、数据、日志、命令、页面或线索
- 应先验证什么
- 推荐的下一步动作是什么

## 7. 风险与注意事项
说明哪些点容易误判、重复劳动或跑偏，哪些方向已经验证过且不建议继续。
```

After section 7, always add a final paragraph titled `下一位 Agent 的第一步建议` with the single best immediate next action.

## Content guidance

- Assume the next agent cannot see the full prior conversation and may only read this handoff file.
- Optimize for restart speed: someone should be able to continue work immediately after reading it.
- Include what was tried already so the next agent does not repeat dead ends.
- If code was changed, name the files and summarize the intent of each change.
- If debugging was done, record observed symptoms, suspected root causes, and what falsified earlier hypotheses.
- If there are blockers, state the blocker, why it blocks progress, and what evidence would unblock it.
- If relevant, note verification status separately: tests run, builds run, diagnostics checked, manual QA performed, and their outcomes.

## Minimal execution checklist

Before finishing, verify:

1. The filename matches `./{yymmdd}-handoff.md`.
2. All seven sections are present in the required order.
3. The document is specific enough that another agent can continue without the old context.
4. Repeated dead ends, rejected directions, and open risks are captured.
5. `下一位 Agent 的第一步建议` is present and actionable.
