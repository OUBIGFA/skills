---
name: code-rules
description: Coding rules and development discipline for all code-related tasks. Use this skill whenever the user asks you to write, modify, debug, refactor, review, or test any code. Always apply these rules during code work, even if the user does not explicitly mention them.
version: 1.0.0
---

# Code Rules

Core coding discipline. Follow every rule below whenever you are writing, modifying, debugging, or reviewing code.

## Simplicity First

- Always choose the simplest, most efficient approach. Never overcomplicate.
- If you write 200 lines and it could be 50, rewrite it.
- Do not write special-case patches. Solutions must be general-purpose.

## Test-Driven Mindset

- "Add validation" means: write tests for invalid inputs, then make them pass.
- "Fix the bug" means: write a test that reproduces the bug, then make it pass.
- "Refactor X" means: ensure tests pass before and after the refactor.

## Evidence Before Judgment

- Never easily affirm or deny the user's viewpoint. Perform thorough evidence review first.
- Before making claims about code behavior, verify with actual execution or inspection.

## Search Before You Build

Before modifying any style, logic, configuration, component, text, or build process:

1. **Search first.** Globally search for related selectors, class names, keywords, variable names, template placeholders, and build artifact sources. For functions, components, and call relationships, prefer structured index or code-graph tools.
2. **Reuse existing control points.** If a dedicated style, function, configuration, or wrapper already exists, modify the original control point. Do not add override rules, duplicate selectors, duplicate functions, bypass configs, or temporary patches.
3. **Only add when necessary.** A new implementation is allowed only when no suitable control point exists or the current design genuinely cannot support the requirement. You must be able to explain why the existing implementation cannot be reused.
4. **Check the diff.** After any modification, review the diff to confirm no duplicate code, meaningless overrides, irrelevant formatting changes, or encoding changes were introduced.

> Lesson learned: Never conclude "no existing control point" just from a local file snippet. Local judgment leads to duplicate code and bloated styles. Always search globally before acting.

## Verify Your Work

- Before reporting results, verify your own work using available tools. Run the code, check the output, confirm it does what was asked.
- For visual work (web apps), view the pages, click through flows, check rendering and behavior.
- For scripts, run against real or representative input and inspect results.
- Try edge cases you can simulate.

## Define Done Before Starting

- Before starting any task, define finishing criteria: what does "done" look like?
- Use that as your checklist before coming back with results.
- If something fails or looks off, fix it and re-test. Do not hand back a first draft for the user to spot-check.
- Only come back when you have confirmed things work, or when you have genuinely hit a wall requiring user input.

## Communication

- When reporting results back, explain what you did and what happened in plain, clear language.
- Avoid jargon, technical implementation details, and code-speak in final responses.
- Write as if explaining to a smart person who is not looking at the code.
- Your actual work (thinking, planning, coding, debugging) stays fully technical and rigorous. Only the communication is simplified.


## UTF-8 Encoding Enforcement

写代码时（不包括文章或 Markdown），凡涉及中文、日文等多字节字符，必须使用 UTF-8 编码。写入文件或输出到控制台前，先确认环境字符集已声明为 UTF-8，禁止出现乱码或截断。