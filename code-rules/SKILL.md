---
name: code-rules
description: Use for code changes, debugging, refactoring, review, or tests. Covers simplicity, reuse, evidence, scope, and completion criteria.
version: 1.0.0
---

# Code Rules

Core coding discipline. Follow every rule below whenever you are writing, modifying, debugging, or reviewing code.

## Simplicity First

- Always choose the simplest, most efficient approach. Never overcomplicate.

- If you write 200 lines and it could be 50, rewrite it.

- Do not write special-case patches. Solutions must be general-purpose.

- When fixing compatibility issues, never hard-code the single sample, domain, filename, string, or format the user happened to report. First identify the general rule behind the failure and the existing control point that owns it, then make the smallest general-purpose change there. The fix must cover the class of equivalent inputs while preserving existing correct behavior.

## Modular Structure

- Do not concentrate all content, logic, UI, state, configuration, and features in a single file.

- Split code into small modules by responsibility, feature, or stable ownership boundary.

- When a file keeps growing, extract focused helpers, components, services, or configuration modules before it becomes hard to maintain.

- New code must be easy to find, understand, replace, and test later.

- Avoid dumping unrelated behavior into an existing file just because it is convenient.

## Test-Driven Mindset

- "Add validation" means: write tests for invalid inputs, then make them pass.

- "Fix the bug" means: write a test that reproduces the bug, then make it pass.

- "Refactor X" means: ensure tests pass before and after the refactor.

- Tests must protect observable behavior, public contracts, rendered output, or produced artifacts. Do not assert production source text, function names, whitespace, or internal structure with regex unless that exact text is the required output contract.

- Prefer DOM, jsdom, browser, API, CLI, snapshot-of-output, or artifact-level checks over source-file string checks.

- Keep fixtures narrow. Load only what the test needs, and add clear assertion messages when a test has multiple checks.

- Compatibility fixes must include behavior-level tests for the reported sample, at least one equivalent same-class input, and an ordinary non-matching input that must not be misclassified.

## Shared Contracts

- Do not copy shared decisions such as escaping, parsing, formatting, routing, validation, or configuration. Find the existing owner and reuse it.

- If duplicate implementations already exist, consolidate toward one source of truth when touching that area. Do not add another local fallback unless the runtime boundary truly requires it and the fallback is documented.

- Shared security-sensitive helpers, especially escaping and sanitization, must not drift across build-time and runtime code.

## Explicit Dependencies

- Avoid hidden coupling through globals, load order, environment state, or template side effects. If such coupling is unavoidable, declare the dependency where it is used and keep ordering in one obvious control point.

- When a project intentionally avoids a bundler or dependency system, document each script's required globals and verify the combined page behavior in a real or simulated browser.

- Do not use brittle source-text tests to compensate for implicit dependencies. Strengthen the dependency boundary or test the runtime behavior directly.

## Evidence Before Judgment

- Never easily affirm or deny the user's viewpoint. Perform thorough evidence review first.

- Before making claims about code behavior, verify with actual execution or inspection.

## Search Before You Build

Before modifying any style, logic, configuration, component, text, or build process:

1.   Search first.   Globally search for related selectors, class names, keywords, variable names, template placeholders, and build artifact sources. For functions, components, and call relationships, prefer structured index or code-graph tools.
2.   Reuse existing control points.   If a dedicated style, function, configuration, or wrapper already exists, modify the original control point. Do not add override rules, duplicate selectors, duplicate functions, bypass configs, or temporary patches.
3.   Only add when necessary.   A new implementation is allowed only when no suitable control point exists or the current design genuinely cannot support the requirement. You must be able to explain why the existing implementation cannot be reused.
4.   Check the diff.   After any modification, review the diff to confirm no duplicate code, meaningless overrides, irrelevant formatting changes, or encoding changes were introduced.

> Lesson learned: Never conclude "no existing control point" just from a local file snippet. Local judgment leads to duplicate code and bloated styles. Always search globally before acting.

## Refactor Boundaries

- Treat large files and long mixed-purpose functions as change-risk signals. When touching one, look for a small responsibility-based extraction that makes the current change safer.

- Split by stable behavior: state lookup, data transformation, DOM construction, event binding, navigation, rendering, and persistence should not be tangled without a clear reason.

- Do not perform broad rewrites just because a file is large. Improve the boundary nearest to the requested change, verify behavior, and leave unrelated code alone.

## Change Impact

- Before editing, identify the file's callers, dependents, public contract, and relevant tests when they are discoverable.
- Update the affected contract and its dependents in the same task; do not leave known broken imports, references, or generated outputs behind.
- Keep the investigation proportional: a typo does not require a repository-wide map, while a shared API or configuration change does.

## Verify Your Work

- Before reporting results, verify your own work using available tools. Run the code, check the output, confirm it does what was asked.

- For visual work (web apps), view the pages, click through flows, check rendering and behavior.

- For scripts, run against real or representative input and inspect results.

- Try edge cases you can simulate.

- Match evidence to the claim: tests prove behavior, builds prove compilation, diffs prove scope, and a checklist proves requirements.
- Use fresh evidence for completion claims. If something was not checked, say so explicitly instead of implying success.

## Define Done Before Starting

- Before starting any task, define finishing criteria: what does "done" look like?

- Use that as your checklist before coming back with results.

- If something fails or looks off, fix it and re-test. Do not hand back a first draft for the user to spot-check.

- Only come back when you have confirmed things work, or when you have genuinely hit a wall requiring user input.

- For complex work, record the stopping point and the remaining unverified risks before handing back the result.

## Communication

- When reporting results back, explain what you did and what happened in plain, clear language.

- Avoid jargon, technical implementation details, and code-speak in final responses.

- Write as if explaining to a smart person who is not looking at the code.

- Your actual work (thinking, planning, coding, debugging) stays fully technical and rigorous. Only the communication is simplified.
