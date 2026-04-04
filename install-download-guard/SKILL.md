---
name: install-download-guard
description: Guardrail for any install/download/setup/change request, AND resource download organizer. Use whenever the user asks to install software, dependencies, skills, plugins, scripts, packages, download and place files, or batch-download/organize resources (models, datasets, assets, archives). Require preflight briefing and explicit confirmation before execution; for resource downloads, also produce a structured manifest and organize files into canonical paths.
---

Enforce a strict preflight-confirm-execute workflow for all installation and download tasks.

## Execute this workflow

1. Produce a preflight briefing and do not execute any install/download action.
2. Wait for explicit confirmation from the user (for example: “确认安装”, “继续执行”, “同意覆盖”).
3. Execute only the confirmed scope.
4. Report post-install verification with concrete evidence.
5. If execution fails, report cause, fix, and next options.

## Preflight briefing checklist (mandatory)

- Source: URL/repository/publisher
- Target install path: full absolute path
- Planned file changes: create/overwrite list
- Key file sizes: at least SKILL.md and primary script/binary
- Dependencies and permission scope
- Risks: overwrite/delete/conflict/network uncertainty
- Rollback plan: delete target and/or restore backup

## Confirmation policy

- Without explicit confirmation, do not execute.
- If overwrite/delete is involved, request a second confirmation.

## Post-install verification output

- Final install path
- Actual files written
- Actual size/version evidence
- Basic usability check result

---

# Part 2: 资源归纳下载 (Resource Download Organizer)

When the user asks to download/collect/organize resources (models, datasets, LoRAs, assets, archives, checkpoint files, etc.), follow this extended workflow on top of the standard preflight guard above.

## Trigger keywords

下载资源、批量下载、下载模型、下载数据集、归纳下载、整理资源、aria2 下载、资源清单、download resources、batch download、collect assets

## Step 1: 资源清单 (Resource Manifest)

Before any download, produce a manifest table:

| # | Name | Source URL | Size (est.) | Target Path | Format | Notes |
|---|------|-----------|-------------|-------------|--------|-------|
| 1 | ... | ... | ... | ... | ... | ... |

Rules:
- Every resource MUST have a concrete target path (absolute) — no "TBD".
- Group related resources under a shared parent directory.
- Estimate size; flag anything > 2 GB with ⚠️.
- If a resource has multiple mirrors/sources, list the preferred one first and note alternates.

## Step 2: 目标路径规范 (Target Path Conventions)

Propose paths following this hierarchy (adapt to project context):

```
D:\Software\<project_name>/
├── models/          # Model weights, checkpoints, safetensors
│   ├── <model_name>/
│   └── loras/
├── datasets/        # Training/eval data
├── assets/          # Images, audio, video, fonts
│   ├── images/
│   └── audio/
├── archives/        # Zips, tars before extraction
└── tools/           # Standalone binaries, scripts
```

- For any local deployment, local install, local service setup, dependency bootstrap, plugin/skill installation, or downloaded runtime bundle on this machine, use `D:\Software\<project_name>` as the unified root unless the user explicitly overrides it.
- Treat `D:\Software` as the canonical parent directory for local software/resource organization on this machine.
- Place downloaded installers and archives under `archives/` inside the project root, not in the Windows Downloads folder.
- Place service code, launch scripts, wrappers, virtual environments, and tool-specific configs under `tools/` inside the project root.
- Place runtime-generated model/cache resources under `models/` when they are part of the deployed stack.
- If the project already has its own directory convention (e.g., ComfyUI `models/checkpoints`), respect it.
- If the user asks to follow this skill's standard and another convention conflicts, prefer the `D:\Software\<project_name>` convention unless the user explicitly wants the project-specific convention instead.
- Never dump files into the project root.
- Propose `mkdir -p` commands in the preflight.

## Step 3: 下载策略 (Download Strategy)

Pick the best tool for the job:

| Scenario | Tool | Example |
|----------|------|---------|
| Single file, small | `curl -L -o` / `wget` | Quick one-off |
| Single file, large/resumable | `aria2c -x16 -s16 -c` | Models, datasets |
| Batch files from list | `aria2c -i urls.txt` | Multiple resources |
| Git repo / LFS | `git clone --depth 1` | HuggingFace repos |
| HuggingFace model | `huggingface-cli download` | Official HF models |
| Torrent / magnet | `aria2c --seed-time=0` | Community shares |
| Authenticated download | `curl -H "Authorization: Bearer ..."` | Gated models |

Rules:
- Default to aria2c for anything > 100 MB (resume support).
- For batch downloads, generate a `urls.txt` or `download.sh` script and show it for confirmation.
- Always use `-c` (continue) flag to support resume.
- If auth tokens are needed, prompt user — never guess or hardcode.

## Step 4: 确认并执行 (Confirm & Execute)

Present the full plan:
1. Manifest table (from Step 1)
2. Directory creation commands
3. Download commands (in execution order)
4. Estimated total size and disk space check

Wait for explicit confirmation, then execute sequentially. Report progress per-file.

## Step 5: 下载后验证 (Post-Download Verification)

For each resource:
- ✅ File exists at target path
- ✅ File size matches expectation (± 5%)
- ✅ File type/format check (e.g., `file <path>` or check magic bytes)
- ✅ SHA256/MD5 check if hash was provided by source
- ❌ Report any failures with cause and retry suggestion

## Step 6: 生成资源索引 (Generate Resource Index)

After all downloads complete, produce or update a `RESOURCES.md` at the project root:

```markdown
# Downloaded Resources

> Last updated: YYYY-MM-DD

| Name | Path | Size | Source | Hash | Date |
|------|------|------|--------|------|------|
| ... | ... | ... | ... | ... | ... |

## Notes
- Any special instructions, version pins, or dependencies between resources.
```

- If `RESOURCES.md` already exists, merge new entries — don't overwrite.
- This file serves as the single source of truth for what's been downloaded and where.
