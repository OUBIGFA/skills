---
name: local-install-deploy-guard
description: Create and review formal local installation and deployment plans for this Windows workstation. Use when the user asks to install software, deploy local services, download resources, organize runtimes, package dependencies, expose local tools as APIs, or design directory layouts for any project. This skill records the machine profile, canonical install root rules, dependency/runtime standards, resource organization conventions, verification requirements, and preflight-confirm-execute workflow for maintainable local deployments under D:\Software.
---

# Local Install & Deploy Guard

Use this skill to plan or execute formal local installation and deployment tasks on this specific machine.

This is a general-purpose local deployment skill.
It is not tied to any single software, framework, or repository.

Use it whenever the user wants to:

- install software locally
- deploy a local service
- download and organize resources
- install runtimes or dependencies
- package a local toolchain
- expose a local tool as an API
- standardize installation paths
- design a maintainable on-disk deployment layout

## Recorded Machine Profile

Treat this machine profile as the default deployment baseline unless the user explicitly overrides it.

### Operating system
- Windows 11 Professional Insider Preview
- x64-based PC
- Locale: zh-CN
- Timezone: Asia/Shanghai

### Hardware
- CPU: Intel Core i7-12700K
- Cores / threads: 12C / 20T
- RAM: 64 GB
- GPU: NVIDIA GeForce RTX 3080 Ti

### Verified software state
- Python installed: 3.13.12
- Node.js installed: v22.14.0
- Docker installed and daemon available
- Java not installed by default
- Conda not installed by default

### Storage baseline
- Multiple large-capacity local drives exist
- Canonical local software root for this machine: `D:\Software`

## Core Rules

### Rule 1: Unified local deployment root
For any local install, deployment, runtime packaging, service wrapper, downloaded installer, downloaded release artifact, dependency bundle, or deployment-related resource, use:

`D:\Software\<project_name>`

unless the user explicitly overrides it.

Do not scatter deployment assets across arbitrary roots.

### Rule 2: Canonical directory layout
Use this structure by default:

```text
D:\Software\<project_name>
├── models\        # model weights, OCR resources, runtime caches
├── datasets\      # samples, fixtures, evaluation inputs
├── assets\        # images, example files, client examples, docs attachments
├── archives\      # installers, zips, jars, wheels, release artifacts
├── tools\         # code, wrappers, scripts, venvs, configs, launchers
├── data\          # runtime state: uploads, outputs, temp, db
├── logs\          # install logs, service logs, access logs
└── RESOURCES.md    # resource index
```

Never dump files into the project root.

### Rule 3: Directory responsibilities
Use these meanings consistently:

- `archives/`: downloaded installers and release assets
- `tools/`: service code, wrappers, scripts, configs, virtual environments
- `models/`: stack-related model files or cached ML/OCR resources
- `datasets/`: sample inputs, fixtures, verification data
- `assets/`: auxiliary static resources and examples
- `data/`: runtime-generated operational state
- `logs/`: operational and installation logs

### Rule 4: Official-first strategy
Prefer installation methods in this order:

1. Official installer or official package-manager path
2. Official package release
3. Official documented source install
4. Custom wrapper/integration only after official runtime is stable

Do not invent unnecessary custom packaging when official installation already exists.

### Rule 5: Quality-first planning
Do not default to “minimum viable” deployment plans.

Produce formal, maintainable, long-term deployment plans with:
- version choices
- path layout
- dependency boundaries
- startup method
- verification steps
- risk notes
- rollback plan

## Runtime Preferences for This Machine

These are defaults, not absolute mandates.

### Python
For formal deployments, prefer:
- Python 3.12 x64 as dedicated deployment runtime
- keep system Python 3.13 untouched unless reuse is explicitly requested

Default project venv path:

`D:\Software\<project_name>\tools\runtime\python312\venv\`

Reason:
- better compatibility for AI/OCR/scientific dependencies
- lower risk than relying on the newest installed Python

### Java
If Java is required and missing, prefer:
- Temurin JDK 17 LTS

Store installer under:
`archives\java\`

Allow standard Windows installation into Program Files.
Record final installed path and version in the deployment report.

### Node.js
Node.js is available and suitable for integrations.
Do not assume it should be the primary runtime unless the target software is Node-first.

### Docker
Docker is available.
Do not default to Docker if:
- the target software is not officially Docker-first
- the user asks for official-standard local deployment
- Docker adds unnecessary indirection

Prefer native deployment when it is the cleaner official path.

## Mandatory Workflow

Follow this exact workflow for any install/download/deploy task.

### Step 1: Preflight only
Before any execution, produce a preflight briefing with:

- Source: official URL / repository / publisher
- Target install path: full absolute path under `D:\Software\<project_name>`
- Planned file changes: key directories/files to create or overwrite
- Key file sizes: installers/packages if available
- Dependencies: runtimes, ports, services, permissions
- Risks: overwrite/conflict/version/network uncertainty
- Rollback plan: uninstall/remove/revert path

Do not execute before explicit confirmation.

### Step 2: Resource manifest
If downloads are involved, produce:

| # | Name | Source URL | Size (est.) | Target Path | Format | Notes |

Every resource must have a concrete absolute target path.

### Step 3: Confirmation
Wait for explicit confirmation such as:
- 确认安装
- 继续执行
- 同意创建
- 同意覆盖

If overwrite/delete is involved, ask for a second confirmation.

### Step 4: Execute confirmed scope
Execute only the confirmed scope.
Do not silently install extra components.

### Step 5: Post-install verification
Report with evidence:

- final install path
- files written
- version evidence
- runtime usability checks
- process/service status if applicable
- endpoint checks if applicable

## Planning Rules

### For local software installs
Always specify:
- official source
- installer/package choice
- exact target root
- where archives are stored
- where runtime is installed
- how version is verified

### For local services
Always specify:
- process layout
- bind address
- port allocation
- config location
- log location
- data location
- startup command
- health check
- retention/cleanup policy if files accumulate

### For wrappers and integrations
When wrapping a local tool:
- keep official runtime beneath the wrapper
- put wrapper code under `tools/`
- put configs under `tools/config/`
- put runtime outputs under `data/`
- put logs under `logs/`

### For OpenAI-compatible APIs
If exposing a non-LLM tool through an API:
- use OpenAI-style auth and file handling where it makes sense
- use custom task/job endpoints when that is the correct abstraction
- do not force non-chat workloads into `/v1/chat/completions` unless the semantics truly fit

## Verification Standards

A deployment plan is incomplete without explicit verification criteria.

Always include:

- runtime version checks
- path existence checks
- package availability checks
- process startup checks
- endpoint health checks if API exists
- representative workload test
- output path verification
- log path verification

## Reporting Format

When producing a deployment plan, structure it as:

1. Goal
2. Machine fit assessment
3. Official deployment path selection
4. Install root and directory layout
5. Resource manifest
6. Dependency/runtime plan
7. Service/process architecture
8. Config and startup layout
9. Verification checklist
10. Risks and rollback

## User Preference Memory

Treat these as default preferences learned from repeated user feedback:

- Prefer formal, complete, high-quality plans
- Avoid “minimal executable” framing
- Follow official standards whenever possible
- Use `D:\Software` as canonical local deployment root
- Organize all deployment assets under a unified folder
- Explain what rules a deployment plan is following
- Show skill content for review before creating files

## Must Not Do

- Do not default to scattered install paths
- Do not mix deployment assets across multiple arbitrary roots
- Do not use ad-hoc roots when `D:\Software\<project_name>` is suitable
- Do not assume the newest installed runtime is automatically best
- Do not skip preflight for install/download actions
- Do not give generic advice without adapting it to this machine

## Tone
Be direct, structured, and formal.
Optimize for maintainability, not shortcut convenience.
