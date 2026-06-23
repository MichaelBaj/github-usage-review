---
id: "repo-architecture-review"
version: "1.1.0"
tags: [architecture, audit, agent, remediation, planning]
mode: agent
---

# Repo Architecture Review

## Description

Architecture + context-efficiency audit of repo's agent customization files across supported platforms (Copilot, Claude). Interactive finding-by-finding decisions, then generates planner-style execution plan under ~/agentic_plans/.

## Inputs

- `scopePath` — Workspace-relative path to audit (default: `.`)
- `planName` — Execution plan folder slug under ~/agentic_plans (default: `architecture-remediation`)
- `branchName` — Git branch to create for remediation planning (optional)
- `contextReportPath` — Workspace-relative path to an existing context-efficiency report (optional)

## Operating Contract

- Two modes: audit first, remediation-planning second.
- Interactive questions for all decision points after findings.
- Every Critical/High/Medium/Low finding must receive user decision.
- Agentic Architecture Guide (`.resources/shared/agentic-architecture-guide.md`) is canonical.
- Do **not** flag missing prompt `tools` frontmatter by default.
- Decision outcomes: `Implement now` | `Defer to follow-up` | `Accept risk` | `Reject finding` | `Need more evidence`
- Capture rationale in execution plan.

---

## Phase 1 — Load the Architecture Reference

Read `.resources/shared/agentic-architecture-guide.md` in full. Use as evaluation framework.

If `contextReportPath` provided, read as supplemental evidence. Validate repo state independently.

---

## Phase 2 — Inventory Customization Artifacts

Find and list every customization file across all agent platforms:

| Layer | Glob pattern |
|---|---|
| Root instructions | `CLAUDE.md`, `.github/copilot-instructions.md` |
| Path instructions | `.github/instructions/**/*.instructions.md` |
| Custom agents | `.github/agents/**/*.agent.md`, `.resources/agents/**/*.md` |
| Prompts | `.github/prompts/**/*.prompt.md`, `.resources/prompts/**/*.md` |
| Skills | `.github/skills/**/SKILL.md`, `.resources/skills/**/*.md` |
| Routing | `routing/{copilot,claude}/**` |
| Reference docs | `.resources/shared/**/*.md` |
| Workspace context | `.vscode/tasks.json`, `.vscode/settings.json` |

Also check: `contextReportPath` if provided, `reports/*always-on-context*.md`.

Read every file in full. Output inventory table: `Layer`, `Path`, `Loaded (Y/N)`.

---

## Phase 3 — Evaluate Against Architecture Principles

Apply the **Placement Rules** and **Evaluation Checklist** from the guide to each artifact.

### 3a. Root Instructions (`CLAUDE.md`, `.github/copilot-instructions.md`)

Check:
- Concise, broadly applicable, free of deep domain detail?
- Defines **behavior**, not workflows or tool inventories?
- Too long (context bloat risk)?
- Inlines large material that should be lazy-loaded?
- Stable rules separated from volatile templates?
- Cross-platform consistency: same intent expressed across all root files?

### 3b. Path Instructions (`*.instructions.md`)

Check:
- Scoped to right `applyTo` glob?
- `applyTo: "**"` where not needed? (burns context every interaction)
- Folder-local, or duplicates root?

### 3c. Skills (`SKILL.md`)

Check:
- Clearly scoped to specialized domain knowledge?
- Contains general rules belonging in root instructions?
- `description` has trigger phrases matching user invocation?
- Gaps for common tasks?

### 3d. Prompts (`*.prompt.md`)

Check:
- Single, focused task with clear inputs?
- `tools` frontmatter complete if declared?
- `description` clearly conveys when to use?
- Acting as workflow engines (multi-task sprawl)?
- Restates numeric rules from another contract?

### 3e. Custom Agents (`*.agent.md`, `.resources/agents/`)

Check:
- Distinct role justifying separate agent?
- Too many (sprawl) or overlap?
- References needed skills and tools?
- Canonical definition in `.resources/agents/` with routing derived?

### 3f. Reference Docs (`.resources/shared/`, `docs/`)

Check:
- Large knowledge moved OUT of root/skills?
- Duplicating agent or skill content?
- Large templates should move to shared resources for on-demand loading?

### 3g. Routing (`routing/{platform}/`)

Check:
- Each platform's routing uses `@ref` pointing to canonical `.resources/` source?
- No content drift between platform routing files?
- Platform-specific adaptations (frontmatter, directory conventions) correctly applied?
- Missing platforms that should have routing?

### 3h. Context-Efficiency Surfaces

Check:
- Large workspace surfaces injecting unrelated content?
- User-memory/runtime issues separated into repo-owned vs platform-owned?
- Large mode-scoped sections only needed for one step?
- Issue caused by runtime rather than repo content?
- Per-turn cost: skills/agents sized appropriately?
- Size guardrails: CLAUDE.md ≤ 4,200 chars; per-agent ≤ 20,000 chars.

For each finding assign:
- Severity: `Critical` | `High` | `Medium` | `Low`
- Category: `Behavior` | `Routing` | `Scoping` | `Prompt design` | `Agent overlap` | `Knowledge placement` | `Tooling`
- Evidence: exact section snippet or line
- Concrete remediation action

---

## Phase 4 — Anti-Pattern Scan

Explicitly check for each anti-pattern from the guide:

| Anti-pattern | What to look for |
|---|---|
| **Giant root file** | Any root instruction file over ~150 lines with deep detail |
| **Skills as dumping grounds** | Skills containing general rules, copy-pasted from root instructions |
| **Agent sprawl** | More than ~6 agents, or agents with overlapping scopes |
| **Prompts as workflow engines** | Prompts doing more than one logical task, or containing deep domain logic |
| **`applyTo: "**"` overuse** | Instructions loaded on every interaction when not needed |
| **Lazy-load bypass** | Large templates, routing docs, or rubrics copied into always-loaded files instead of moved to `resources/` |
| **Volatile workspace dump** | Large `.vscode/tasks.json` inventories or other workspace metadata unrelated to repo workflows |
| **Unscoped memory spillover** | Evidence that unrelated memory content crowds out domain-relevant notes |
| **Cross-file contract drift** | Different files restating the same rule with different numbers, thresholds, or exceptions |
| **Cross-platform intent drift** | Same logical rule expressed inconsistently across CLAUDE.md, copilot-instructions.md, and routing wrappers |
| **Prompt tools false positive** | Findings that flag missing prompt `tools` despite repo policy explicitly allowing omission |
| **Compressing normative or syntactic surfaces** | Compression applied to YAML frontmatter, code fences, contract text, checklists, or numeric thresholds |
| **Silent auto-invoke routing** | Root agent delegates to a sub-agent without the routing card |
| **Per-agent scaffolding inline** | Mermaid theme, planner protocol, category rules, or output templates embedded in agent file instead of `resources/` |
| **Single-platform artifact** | Canonical content placed in only one platform's routing without `@ref` to `.resources/` canonical source |

---

## Phase 5 — Findings Report

Produce structured findings report by severity:

```
## Architecture Review — Recommendations

### Critical (breaks agent behavior)
- **[File]**: Issue.
  Evidence: <section/line>
  Recommendation: <exact change>
  Rationale: <principle>

### High / Medium / Low
- ...

### Strengths
- ...
```

Each finding: file path (linked), evidence, concrete recommendation, architectural principle, validation step.

End with findings register table:

| ID | Severity | File | Finding | Recommendation |
|---|---|---|---|---|

---

## Phase 6 — Interactive Decision Workshop (Required)

### 6a. Session setup

Ask:
1. Remediation horizon: this sprint / next sprint / backlog only
2. Risk tolerance: conservative / balanced / aggressive
3. Constraints: release window, no-touch files, ownership

### 6b. Per-finding decision loop

For each finding (Critical → High → Medium → Low):
- Present summary, evidence, recommended remediation
- Decision options: Implement now | Defer | Accept risk | Reject | Need more evidence
- If `Need more evidence`: gather, re-present, ask again
- Record decision + rationale in register

### 6c. Dependency clarification

After all decisions:
- Which must happen first?
- Which run in parallel?
- Required reviewers/owners?

---

## Phase 7 — Generate Planner-Style Execution Plan

Using planner agent workflow, generate plan under `~/agentic_plans/<planName>/`.

Required:
- `00-overview.md` + phase files (`01-phase-*.md`, etc.)
- YAML headers, status lifecycle fields
- Goals → Features → Modules → Tasks decomposition
- Effort estimates, risks, commit checkpoints
- Decision register: finding ID → user decision + rationale
- Validation commands per phase

### Branch workflow

Before writing: propose branch `$USER/<work-item>`, confirm, create.

---

## Output Contract

1. Findings report (severity ordered)
2. Decision workshop summary (all IDs resolved)
3. Execution plan file index
4. Top 3 immediate actions
5. Validation checklist for highest-risk remediations

## References

- [Agentic Architecture Guide](.resources/shared/agentic-architecture-guide.md)
