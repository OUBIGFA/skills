---
name: verification-before-completion
description: Use for explicit verification requests or high-risk release, commit, or delivery checks. General code completion evidence is covered by code-rules.
version: 3.0
---

# Verification Before Completion

Use this skill when the user asks for a verification pass, release readiness check, commit or delivery gate, or when the change is unusually risky. For ordinary code work, use the shorter evidence rules in `code-rules`.

## Evidence mapping

- Tests prove observable behavior and regression coverage.
- Builds prove compilation or packaging.
- A diff proves the scope of edits.
- A requirements checklist proves requested outcomes.
- Runtime inspection proves a browser, CLI, service, or generated artifact behaves as expected.

Use fresh evidence that matches the claim. Do not treat a previous run, an assumption, or a source-code glance as proof. If a check was not run, report that limitation explicitly.

## High-risk gate

For release, commit, deployment, destructive migration, or external delivery:

1. Identify the exact claim and the command or observation that can prove it.
2. Run the smallest complete relevant check and inspect its exit status and important output.
3. Check the diff and affected artifacts for unintended changes.
4. Report pass, failure, or unverified status with evidence and remaining risk.
