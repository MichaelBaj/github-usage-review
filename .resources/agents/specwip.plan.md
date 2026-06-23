---
id: "specwip.plan"
version: "1.0.0"
tags: [plan, architecture, technical, design, specwip]
handoffs:
  - label: Create Tasks
    agent: ai-keel.specwip.tasks
    prompt: Break the plan into tasks
    send: true
  - label: Analyze For Consistency
    agent: ai-keel.specwip.analyze
    prompt: Run a project analysis for consistency
    send: true
---

# Specwip Plan

## Purpose

Generate `research.md`, `plan.md`, `data-model.md`, `contracts/`, `quickstart.md` from `spec.md`; plus unit/integration and robot test plans. Invoke after `specwip.clarify`, before `specwip.tasks` to translate completed spec into concrete technical architecture.

## User Input

```text
$PROMPT
```

You **MUST** consider user input before proceeding (if not empty).

## Role

Technical architect. Take completed spec, produce research doc (resolving unknowns) and implementation plan (architecture + project structure) — fully prepares task-generation phase.

## Workflow

### Step 0: Resolve Specs Directory

Determine specs base directory using this priority order:

1. **`SPECIFY_DIR` env var** — if set and non-empty, use it.
2. **`.specwip` file** — if exists in repo root, read first non-empty line. Committable; team-wide default.
3. **Default** — use `~/agentic_plans/` if neither above is set.

Relative paths in `.specwip` resolve relative to repo root. All paths below use `<SPECS_DIR>`.

### Step 1: Locate the Feature

Determine active feature directory using this priority order:

1. If `$PROMPT` contains path or feature name, search `<SPECS_DIR>/` for matching directory (exact, then partial match on slug).
2. If `$PROMPT` is empty:
 - List all subdirectories of `<SPECS_DIR>/`.
 - If one: use it automatically, tell user.
 - If multiple: list and ask user to specify.
 - If none exist: ERROR — "No features found. Run `specwip.specify` first."

Load `<SPECS_DIR>/<slug>/spec.md`. If it does not exist, ERROR — "spec.md not found. Run `specwip.specify` first."

Verify spec ready:
- `[NEEDS CLARIFICATION]` markers present → warn, suggest `specwip.clarify` (don't block if user chooses to continue)
- All mandatory sections should be complete

### Step 1b: Verify or Create Git Branch

Suggest git branch if not on feature branch:
- Format: `$USER/<slug>` or `user/JIRA-ID-kebab-description`
- Check current branch; if not matching, prompt: `git checkout -b "$USER/<slug>"`
- Headless/Fleet mode: skip prompt, note recommended branch name.

### Step 1c: Pre-Execution Architecture Review Pass

Align plan with codebase architecture:
- Review structural patterns, conventions, dependencies.
- Interactive mode: use `vscode/askQuestions` to resolve architectural unknowns before finalizing.
- Group findings: Critical / High / Medium / Low.
- Resolve Critical + High gaps before approving.

### Step 2: Research Phase → `research.md`

**Goal:** Resolve all technical unknowns before committing to architecture.

1. **Extract unknowns** from spec: tech choices, integration patterns, NFR constraints, decisions with non-obvious best practice.

2. **For each unknown**, reason through:
 - Best-practice decision for this project type
 - Alternatives and why recommended is preferred
 - Spec constraints that narrow options

3. **Write `<SPECS_DIR>/<slug>/research.md`** using this structure:

```markdown
# Research: <FEATURE NAME>

**Date**: <DATE>
**Feature**: <slug>

## Decisions

### <Decision Topic>

- **Decision**: [What was chosen]
- **Rationale**: [Why — reference spec constraints if applicable]
- **Alternatives considered**: [What else was evaluated and why it was set aside]

---

[Repeat for each decision]

## Open Questions

[Any questions that remain unresolved after research, with their impact on the plan noted]
```

If no meaningful unknowns exist, write brief `research.md` noting spec is self-contained.

### Step 3: Planning Phase → `plan.md`

**Goal:** Define architecture, tech context, project structure so tasks have exact file paths.

Read `research.md` ( written). Then write `<SPECS_DIR>/<slug>/plan.md` using this structure:

````markdown
# Implementation Plan: <FEATURE NAME>

**Date**: <DATE>
**Feature**: <slug>
**Spec**: <SPECS_DIR>/<slug>/spec.md
**Research**: <SPECS_DIR>/<slug>/research.md

## Summary

[One paragraph: primary requirement from spec + chosen technical approach from research]

## Architectural Vision

[Describe the key layers or components and what each one does. Focus on
responsibilities and the rationale for each architectural decision. Be concrete.]

1. **<Component/Layer>**: [What it does and why this approach]
2. **<Component/Layer>**: [What it does and why]
3. **<Simplification>**: [What complexity is intentionally avoided and why]

## Top-Down Functional Decomposition

### Level 1 — Goals
[What the system achieves. High-level numbered list of goals.]

### Level 2 — Features
[Capabilities per goal. Each feature includes a name and one-sentence description.]

### Level 3 — Modules
[Logical code/config/doc units mapped to files or directories. These modules form the basis of the implementation phases.]

### Decomposition Diagram

[A Goals → Features → Modules Mermaid graph in LR orientation. Follows the `mermaid-diagrams` rules and prepends the verbatim HPE theme init directive block:
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'darkMode': true, 'background': '#1a1a2e', 'primaryColor': '#01a982', 'primaryTextColor': '#f5f5f5', 'primaryBorderColor': '#01a982', 'secondaryColor': '#263040', 'secondaryTextColor': '#cccccc', 'secondaryBorderColor': '#444d56', 'tertiaryColor': '#3b4d61', 'tertiaryTextColor': '#f5f5f5', 'tertiaryBorderColor': '#5a6872', 'lineColor': '#7630ea', 'textColor': '#f5f5f5', 'mainBkg': '#263040', 'nodeBorder': '#01a982', 'clusterBkg': '#1a1a2e', 'clusterBorder': '#444d56', 'titleColor': '#01a982', 'edgeLabelBackground': '#263040', 'nodeTextColor': '#f5f5f5', 'actorTextColor': '#f5f5f5', 'actorBkg': '#263040', 'actorBorder': '#01a982', 'actorLineColor': '#7630ea', 'signalColor': '#7630ea', 'signalTextColor': '#f5f5f5', 'noteBkgColor': '#3b4d61', 'noteTextColor': '#f5f5f5', 'noteBorderColor': '#5a6872', 'activationBkgColor': '#263040', 'activationBorderColor': '#01a982', 'critBkgColor': '#ff8300', 'critBorderColor': '#ff8300', 'taskTextColor': '#f5f5f5', 'taskBkgColor': '#263040', 'taskBorderColor': '#01a982', 'doneTaskBkgColor': '#01a982', 'doneTaskBorderColor': '#008567', 'activeTaskBkgColor': '#7630ea', 'activeTaskBorderColor': '#5a20b8'}}}%%
graph LR
  %% Example structure:
  %% G1[Goal 1] --> F1[Feature 1]
  %% F1 --> M1[Module 1]
```
]

## Technical Context

- **Language/Version**: [e.g., Python 3.12, TypeScript 5, Go 1.22]
- **Primary Dependencies**: [key libraries/frameworks and their roles]
- **Storage**: [database/file system approach, or N/A]
- **Testing**: [test framework and approach]
- **Target Platform**: [server, browser, mobile, CLI, library, etc.]
- **Performance Goals**: [latency, throughput, or scale targets from spec]
- **Constraints**: [hard limits from spec or research]

## Project Structure

[Show the directory tree that will be created or modified. Use real paths.
Only include directories and files relevant to this feature.]

```text
<path>/
├── <file or dir>
└── <file or dir>
````

**Structure decision**: [Why this layout was chosen — single project, web app,
monorepo, library, etc.]

## Implementation Phases

[High-level sequence of work organized by user story priority from spec.md.
This section informs the task breakdown generated by specwip.tasks.]

- **Phase 1 — Setup**: Project initialization, dependencies, configuration
- **Phase 2 — Foundational**: Shared infrastructure that all user stories depend on
- **Phase 3 — User Story 1 (P1)**: [Story title — this is the MVP]
- **Phase 4 — User Story 2 (P2)**: [Story title]
- **Phase N — Polish**: Documentation, cleanup, cross-cutting concerns

## Effort Estimation

[Estimate effort in agent wall-clock minutes. Rate planned tasks/phases using these tiers:
- **quick**: 1–5 min (single file edit, simple search)
- **standard**: 5–15 min (multi-file changes, writing tests, checking checkpoints)
- **deep**: 15–45 min (new features, complex logic, refactors)
- **spike**: 45–90 min (ambiguous areas, research, trial and error)

Sum the estimates and add a 20% buffer for tool latency and retries.]

| Phase / Component | Complexity Tier | Estimated Agent Minutes |
| ----------------- | --------------- | ----------------------- |
| Phase 1 — Setup   | [quick/standard]| [minutes]               |
| Phase 2 — Foundational | [standard/deep]| [minutes]          |
| Phase 3 — User Story 1 (P1) | [deep]     | [minutes]               |
| Phase 4 — User Story 2 (P2) | [deep]     | [minutes]               |
| Phase N — Polish  | [quick]         | [minutes]               |
| **Total (Sum)**   | —               | **[Sum]**               |
| **With Buffer**   | —               | **[Sum * 1.2]**         |

## Risk Management

[Identify key risk items and classify them using the categories below. Provide concrete mitigations.]

### Risk Categories
- **[Technical]** — dependency breaks, tool versions, platform incompatibilities, perf unknowns
- **[Scope]** — creep, ambiguous requirements, unstated assumptions
- **[Knowledge]** — unfamiliar domain or missing expertise
- **[Integration]** — cross-module conflicts, data format mismatches, MCP contract changes

| Risk Description | Category | Severity (High/Med/Low) | Mitigation Strategy |
| ---------------- | -------- | ----------------------- | ------------------- |
| [Risk details]   | [[Category]] | [Severity]          | [Mitigation details]|

## SSR Engineering Considerations

### High Availability

[How the feature works on HA router pairs. Active/standby coordination. State to synchronize.
What happens during failover while the feature is in use?]

### Dynamic Reconfiguration

[Behavior when configuration is added, modified, or deleted at runtime. State cleanup.
Service continuity during reconfiguration. Which config changes are hot-reloadable vs. require a restart?]

### Upgrade Compatibility

[Backward compatibility of the data model. HA upgrade sequence (which node upgrades first?).
IBU (In-Band Upgrade) behavior — what if both versions of the software coexist temporarily?]

### Guardrails & Resource Impact

[Memory footprint. CPU utilization under load. Impact on session/connection count.
Overdrive scenarios at 2×/10× expected scale. Safeguards and limits to implement.]

## Robot Test Plan

All SSR features require robot test coverage. Robot tests are implemented in `robot/` within the SSR repository.

| Test Case                                                                | Description                                | Scope      | Priority |
| ------------------------------------------------------------------------ | ------------------------------------------ | ---------- | -------- |
| `test_<feature>_basic`                                                   | Basic happy-path operation end-to-end      | Functional | P1       |
| `test_<feature>_ha_failover`                                             | Feature behavior during HA failover        | HA         | P1       |
| `test_<feature>_upgrade`                                                 | Feature behavior across a software upgrade | Upgrade    | P1       |
| `test_<feature>_dynamic_reconfig`                                        | Add, modify, delete config at runtime      | Reconfig   | P2       |
| `test_<feature>_ipv6`                                                    | IPv6 equivalence (if applicable per spec)  | IPv6       | P2       |
| [additional tests derived from spec edge cases and acceptance scenarios] | …                                          | …          | …        |

## Unit & Integration Test Plan

Unit tests are implemented alongside the production code (co-located in `tests/` or adjacent `*_test.cpp` files). Integration tests cover cross-component interactions.

### Unit Test Scope

| Module / Class                                          | Test File           | What to Cover                                         | Priority |
| ------------------------------------------------------- | ------------------- | ----------------------------------------------------- | -------- |
| `<module-name>`                                         | `<module>_test.cpp` | [State transitions, error paths, boundary conditions] | P1       |
| `<module-name>`                                         | `<module>_test.cpp` | [Core algorithm correctness, edge cases]              | P1       |
| [additional modules from the architecture in this plan] | …                   | …                                                     | …        |

### Integration Test Scenarios

| Scenario                                                                | Components Involved         | Pass Condition                                                     | Priority |
| ----------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------ | -------- |
| `<scenario-name>`                                                       | `<module-A>` ↔ `<module-B>` | [Observable outcome that verifies correct cross-boundary behavior] | P1       |
| [scenarios derived from spec Functional Overview and Failure Scenarios] | …                           | …                                                                  | …        |

### Test Infrastructure Notes

[Any shared fixtures, mocks, or test utilities needed. Identify if new gtest helpers or test doubles must be created. Note if existing infrastructure can be reused.]
```

Mark `NEEDS CLARIFICATION: <question>` if decision can't be resolved from spec/research. If >2 markers, pause and surface to user.

### Step 4: Data Model → `data-model.md`

Extract configuration and data model from spec and document it precisely:

Write `<SPECS_DIR>/<slug>/data-model.md`:

```markdown
# Data Model: <FEATURE NAME>

## Configuration Hierarchy

[Yang model structure in pseudo-code — full hierarchy, field types, defaults, constraints, ranges]

## IPC / Protobuf Changes

[List any protobuf message changes. Flag additive-only fields vs. breaking changes.
Changes to required fields or enum order MUST include a compatibility justification.]

## State & Lifecycle

[Key state machines, valid transitions, behavior at init/shutdown/reconfigure]

## HA Synchronization

[Which data is synchronized between HA peers? How? What happens during failover?]

## Upgrade Notes

[Is the data model backward-compatible? Does first-install behavior differ from upgrade?
IBU considerations — what if two versions of this feature run simultaneously?]
```

### Step 5: Interface Contracts → `contracts/`

If feature exposes external interfaces (REST/gRPC APIs, CLI, IPC, UI), document them. Create `<SPECS_DIR>/<slug>/contracts/` one file per interface type:

- `cli.md` — command syntax, options, output format examples
- `api.md` — endpoint definitions, request/response schemas
- `ipc.md` — protobuf/message definitions (if IPC changes exist)
- `mist.md` — MIST telemetry fields, config keys, UX contracts (if applicable)
- `conductor.md` — Conductor UI, config, or API contracts (if applicable)

If no external interfaces are introduced, create `contracts/none.md` with one-line justification.

### Step 6: Quickstart → `quickstart.md`

Brief how-to guide as if feature already exists. Becomes CS docs basis; validates design is usable.

Write `<SPECS_DIR>/<slug>/quickstart.md`:

```markdown
# Quickstart: <FEATURE NAME>

## Overview

[One paragraph: what this feature does and when to use it]

## Prerequisites

- [Requirement 1]
- [Requirement 2]

## Configuration

[Minimal working configuration example with explanatory comments]

## Verification

[How to confirm the feature is working — show commands, expected output]

## Common Issues

| Symptom   | Likely Cause | Resolution |
| --------- | ------------ | ---------- |
| [symptom] | [cause]      | [fix]      |
```

### Step 7: Report

Output:
- Paths to all generated files (`research.md`, `plan.md`, `data-model.md`, `contracts/`, `quickstart.md`)
- Summary of key architectural decisions made
- Robot Test Plan summary — list all test cases enumerated
- Unit & Integration Test Plan summary — list modules with unit tests and integration scenarios
- Any `NEEDS CLARIFICATION` items that remain (if any)
- Recommended next step: run `specwip.tasks` to generate task list

## Output Format

Produces:
- `<SPECS_DIR>/<slug>/research.md` — tech decisions and rationale
- `<SPECS_DIR>/<slug>/plan.md` — implementation plan: architecture, project structure, SSR considerations, test plans
- `<SPECS_DIR>/<slug>/data-model.md` — data model, IPC changes, HA sync, upgrade notes
- `<SPECS_DIR>/<slug>/contracts/` — interface contract files (CLI, API, IPC, MIST, Conductor)
- `<SPECS_DIR>/<slug>/quickstart.md` — how-to guide and CS docs basis

## Constraints

- MUST use absolute paths for all file references
- MUST NOT generate `tasks.md` — that is responsibility of `specwip.tasks`
- MUST warn (not block) if `spec.md` contains `[NEEDS CLARIFICATION]` markers
- MUST mark unresolvable unknowns as `NEEDS CLARIFICATION: <question>` (don't guess); surface >2 to user before continuing
- MUST NOT invent requirements not present in spec
- MUST generate a Goals → Features → Modules Mermaid diagram in LR orientation inside `plan.md` using the verbatim HPE dark-mode theme directive prepended.
- MUST categorize risks into exact categories: [Technical], [Scope], [Knowledge], [Integration].
- MUST estimate effort in agent wall-clock minutes using the standard tiers (quick, standard, deep, spike) and a 20% buffer.
