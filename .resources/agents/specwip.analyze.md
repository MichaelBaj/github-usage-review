---
id: "specwip.analyze"
version: "1.0.0"
tags: [spec, analysis, quality, consistency, specwip]
---

# Specwip Analyze

## Purpose

Non-destructive cross-artifact consistency analysis: `spec.md`, `plan.md`, `tasks.md`. Invoke to verify alignment before implementation.

## User Input

```text
$PROMPT
```

You **MUST** consider user input before proceeding (if not empty).

## Goal

Find inconsistencies, duplications, ambiguities, underspecified items across three artifacts before implementation. MUST run only after `specwip.tasks` produces complete `tasks.md`.

## Process

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
 - If none: ERROR — "No features found. Run `specwip.specify` first."

Derive absolute paths:
- SPEC = `<SPECS_DIR>/<slug>/spec.md`
- PLAN = `<SPECS_DIR>/<slug>/plan.md`
- TASKS = `<SPECS_DIR>/<slug>/tasks.md`

If `spec.md` is missing: ERROR — "spec.md not found. Run `specwip.specify` first."
If `plan.md` is missing: ERROR — "plan.md not found. Run `specwip.plan` first."
If `tasks.md` is missing: ERROR — "tasks.md not found. Run `specwip.tasks` first."

### Step 2: Load Artifacts (Progressive Disclosure)

Load minimal context from each:

**From spec.md:**
- Overview/Context
- Functional Requirements
- Non-Functional Requirements
- User Stories
- Edge Cases (if present)

**From plan.md:**
- Architecture/stack choices
- Data Model references
- Phases
- Technical constraints

**From tasks.md:**
- Task IDs
- Descriptions
- Phase grouping
- Parallel markers [P]
- Referenced file paths

### Step 3: Build Semantic Models

Build internal reps (don't output raw artifacts):

- **Requirements inventory**: each functional + non-functional req with stable key (e.g., "User can upload file" → `user-can-upload-file`)
- **User story/action inventory**: discrete user actions with acceptance criteria
- **Task coverage mapping**: map each task to requirements/stories (by keyword or explicit ID)

### Step 4: Detection Passes (Token-Efficient Analysis)

High-signal findings only. Limit 50 total; aggregate overflow.

#### A. Duplication Detection

- Identify near-duplicate requirements
- Mark lower-quality phrasing for consolidation

#### B. Ambiguity Detection

- Flag vague adjectives (fast, scalable, secure, intuitive, robust) lacking measurable criteria
- Flag unresolved placeholders (TODO, TKTK, ???, `<placeholder>`, `[NEEDS CLARIFICATION]`, etc.)

#### C. Underspecification

- Requirements with verbs but missing object or measurable outcome
- User stories missing acceptance criteria alignment
- Tasks referencing files or components not defined in spec/plan

#### D. Coverage Gaps

- Requirements with zero associated tasks
- Tasks with no mapped requirement/story
- Non-functional requirements not reflected in tasks (e.g., performance, security)

#### E. Inconsistency

- Terminology drift (same concept named differently across files)
- Data entities referenced in plan but absent in spec (or vice versa)
- Task ordering contradictions (e.g., integration tasks before foundational setup tasks without dependency note)
- Conflicting requirements (e.g., one requires Next.js while other specifies Vue)

### Step 5: Severity Assignment

Prioritize findings:

- **CRITICAL**: Missing core spec artifact, or requirement with zero coverage that blocks baseline functionality
- **HIGH**: Duplicate or conflicting requirement, ambiguous security/performance attribute, untestable acceptance criterion
- **MEDIUM**: Terminology drift, missing non-functional task coverage, underspecified edge case
- **LOW**: Style/wording improvements, minor redundancy not affecting execution order

### Step 6: Produce Compact Analysis Report

Output Markdown report (no writes):

```markdown
## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | ----------- | -------- | ---------------- | ---------------------------- | ------------------------------------ |
| A1 | Duplication | HIGH | spec.md:L120-134 | Two similar requirements ... | Merge phrasing; keep clearer version |
```

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
| --------------- | --------- | -------- | ----- |

**Unmapped Tasks:** (if any)

**Metrics:**

- Total Requirements
- Total Tasks
- Coverage % (requirements with >=1 task)
- Ambiguity Count
- Duplication Count
- Critical Issues Count

### Step 7: Provide Next Actions

At end of report, output concise Next Actions block:

- If CRITICAL issues exist: Recommend resolving before running `specwip.implement`
- If only LOW/MEDIUM: User may proceed, but provide improvement suggestions
- Provide explicit command suggestions: e.g., "Re-run `specwip.clarify` to resolve ambiguity in requirement X", "Re-run `specwip.plan` to address architecture gap", "Re-run `specwip.tasks` to add coverage for 'performance-metrics'" if needed

### Step 8: Offer Remediation

Ask user: "Would you like me to suggest concrete remediation edits for top N issues?" (Do NOT apply them automatically.)

## Output Format

Produces:
- Markdown analysis report in chat (no writes)
- Coverage summary table mapping requirements to tasks
- Metrics summary (total requirements, tasks, coverage %, issue counts)
- Actionable next steps with explicit command suggestions

## Constraints

- **STRICTLY READ-ONLY**: MUST NOT modify any files — output analysis report only
- MUST NOT run before `specwip.tasks` has produced complete `tasks.md`
- MUST NOT hallucinate missing sections — if absent, report them accurately
- MUST NOT apply remediation automatically — offer suggestions only, require explicit user approval
- Findings table MUST be limited to 50 rows; aggregate overflow in summary
- Rerunning without changes MUST produce consistent finding IDs and counts

## Operating Principles

### Context Efficiency

- **Minimal high-signal tokens**: actionable findings only, not exhaustive docs
- **Progressive disclosure**: Load artifacts incrementally; don't dump all content into analysis
- **Token-efficient output**: Limit findings table to 50 rows; summarize overflow
- **Deterministic results**: rerun without changes → consistent IDs and counts

### Analysis Guidelines

- **NEVER modify files** (this is read-only analysis)
- **NEVER hallucinate missing sections** (if absent, report them accurately)
- **Use examples over exhaustive rules** (cite specific instances, not generic patterns)
- **Report zero issues gracefully** (emit success report with coverage statistics)
