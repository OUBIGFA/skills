---
name: clean-code
description: Use for focused readability or maintainability review about naming, unnecessary complexity, or local duplication. General code work uses code-rules.
allowed-tools: Read, Write, Edit
version: 3.0
---

# Clean Code

Use this skill only when the user asks specifically about readability, naming, local duplication, or unnecessary complexity. Follow `code-rules` for scope, testing, dependencies, and completion.

## Review points

- Prefer clear names that reveal intent; avoid unexplained abbreviations and magic values.
- Keep functions and modules focused on one stable responsibility.
- Inline trivial one-use helpers; extract behavior only when it creates a useful boundary.
- Remove duplication toward the existing source of truth instead of adding another helper or override.
- Prefer guard clauses and simple control flow when they make the behavior clearer.
- Do not refactor unrelated code or apply a style preference without a concrete readability or maintenance benefit.

## Output

Report only actionable findings with the location, problem, consequence, and smallest reasonable remedy. If the code is clear enough, say so briefly and do not invent cleanup work.
