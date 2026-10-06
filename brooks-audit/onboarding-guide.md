# Codebase Onboarding Guide

**Purpose:** Produce a newcomer-friendly tour of the codebase. This is NOT a diagnostic
report — no Health Score, no Iron Law findings. Focus on explanation and orientation.

---

## Process

### Step 1: Map the Territory

- Read top-level structure (same as architecture-guide Step 0)
- Output: a plain-language overview of what each top-level module does (one sentence each)
- Group into layers: "Things users interact with", "Business logic", "Infrastructure"

### Step 2: Draw the Dependency Map

Use architecture audit Step 1 for relationship direction, evidence, and graph checks;
do not run the risk scan for a tour. Use a compact table for a simple structure. When a
graph helps, color nodes by **recommended reading order**, not severity:

- 🔵 Blue (`#339af0`): start here — entry points, core domain
- 🟣 Purple (`#9775fa`): read next — supporting modules
- ⚪ Gray (`#ced4da`): read last — infrastructure, generated code, utilities

Add numbered labels: `CoreModule["1. CoreModule"]`
Keep the numbers and labels readable without color. Use the same module names in the
map and guide, and give key source locations beside the map.

```
classDef start fill:#339af0,color:#fff
classDef next fill:#9775fa,color:#fff
classDef last fill:#ced4da
```

### Step 3: Highlight Key Conventions

Identify and document patterns the codebase follows:
- Naming conventions (file naming, class naming, variable naming)
- Directory organization pattern (feature-based? layer-based? hybrid?)
- Error handling pattern (exceptions? result types? error codes?)
- Testing convention (co-located? separate directory? naming pattern?)
- Dependency injection pattern (if any)

### Step 4: Mark Danger Zones

For each module with known complexity or coupling issues, add a brief warning:
- "OrderService: high complexity, only modify with full test suite running"
- "legacy/: no tests, use Characterization Tests before changing"

Do NOT use Iron Law format — use plain warnings. This is orientation, not diagnosis.

### Step 5: Build a Domain Glossary

Define the domain terms needed to follow the tour. Use the same term for the same concept
throughout. Keep code identifiers unchanged and explain them in plain language; do not
add terms just to meet a count.

### Step 6: Suggest First Tasks

Based on the dependency map, suggest 2-3 low-risk areas where a new developer could make
their first contribution: modules with good test coverage, clear boundaries, low coupling.

---

## Output Template

```
# Codebase Tour: [Project Name]

## Overview
[2-3 sentence summary of what the project does and its tech stack]

## Module Map
[Graph with reading-order labels, or a compact table; scope and key source locations]

## Module Guide
[One paragraph per top-level module: what it does, what it depends on, key files to read]

## Conventions
[Bullet list of patterns this codebase follows]

## Danger Zones
[Bullet list of areas to be careful with, or "None identified" if the codebase is clean]

## Domain Glossary
| Term | Meaning |
|------|---------|

## Suggested First Tasks
[2-3 concrete suggestions for a new developer's first PR]
```
