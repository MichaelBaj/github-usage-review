---
id: "specwip.implement"
version: "1.0.0"
tags: [implementation, tasks, execution, coding, specwip]
---

# Specwip Implement

## Purpose

Execute implementation plan phase by phase from `tasks.md`. Marks tasks complete as it goes. Invoke when ready to write code for fully planned feature.

## User Input

```text
$PROMPT
```

You **MUST** consider user input before proceeding (if not empty).

## Role

Senior software engineer executing well-defined implementation plan. Work through `tasks.md` phase by phase, writing code that precisely matches architecture in `plan.md` and requirements in `spec.md`, marking each task complete.

## Workflow

### Step 0: Resolve Specs Directory

Determine specs base directory using this priority order:

1. **`SPECIFY_DIR` env var** — if set and non-empty, use it.
2. **`.specwip` file** — if exists in repo root, read first non-empty line. Committable; team-wide default.
3. **Default** — use `~/agentic_plans/` if neither above is set.

Relative paths in `.specwip` resolve relative to repo root. All paths below use `<SPECS_DIR>`.

### Step 1: Locate the Feature

Determine active feature directory using this priority order:

1. If `$PROMPT` contains path or feature name, search `<SPECS_DIR>/` for matching directory (exact, then partial match).
2. If `$PROMPT` is empty:
 - List all subdirectories of `<SPECS_DIR>/`.
 - If one: use it automatically, tell user.
 - If multiple: list and ask user to specify.
 - If none exist: ERROR — "No features found. Run `specwip.specify` first."

### Step 2: Load Implementation Context

Read following files in feature directory. All are required unless noted.

| File | Required | Purpose |
| ------------- | ---------- | ------------------------------------------ |
| `tasks.md` | ✅ Required | Complete task list and phase structure |
| `plan.md` | ✅ Required | Tech stack, architecture, exact file paths |
| `spec.md` | ✅ Required | User stories and acceptance criteria |
| `research.md` | If present | Technical decisions and constraints |

If `tasks.md` is missing, ERROR — "tasks.md not found. Run `specwip.tasks` first."
If `plan.md` is missing, ERROR — "plan.md not found. Run `specwip.tasks` first."

### Step 3: Pre-Flight Check

Before writing code:

1. **Review incomplete tasks**: Parse `tasks.md` and display summary of pending work:
 ```
 Phases found: N
 Pending tasks: N
 Completed tasks: N
 ```

2. **Identify resumption point**: If some tasks are already marked `[x]`, start from first `[ ]` task. Tell user where execution is resuming from.

3. **Check for existing tests**: Discover any test runner configuration in repository (e.g., `package.json` scripts, `pytest.ini`, `Makefile`, `Cargo.toml`, `.github/workflows/`). Note which test command(s) are available. If tests are found, they will be run after each task (see Step 6).

### Step 4: Project Setup Verification

Before implementing feature code, ensure repo has appropriate ignore files. Check for and create/update as needed:

- **`.gitignore`** (if this is git repository): verify it covers tech stack from `plan.md`
- **Technology-specific ignores**: detect from `plan.md`'s tech stack and create any that are missing

Do not overwrite existing ignore files — only append missing critical patterns.

Common patterns by technology (from `plan.md`):
- **Node.js/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
- **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
- **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`
- **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
- **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`
- **Universal**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.env`

### Step 5: Phase-by-Phase Execution

Execute all phases in order. Within each phase, run sequential tasks in order. Run `[P]`-marked tasks in parallel where they touch different files.

For **each task**:

1. Read task description carefully.
2. Verify file path against `plan.md`'s Project Structure. If path doesn't match, use plan as authority.
3. Implement task completely — do not skip or stub unless task explicitly says "scaffold".
4. Run test gate (Step 6).
5. Mark task complete in `tasks.md`: change `- [ ]` to `- [x]`.
6. Report: `✓ T<NNN> — <brief description of what was done>`

**Do not proceed to next task until current task is marked `[x]`.**

#### Phase checkpoints

When phase checkpoint is reached (as defined in `tasks.md`):
- Report checkpoint clearly: `🏁 Checkpoint: <Phase name> complete`
- Summarize what was built/established
- Note which user stories or capabilities are now testable

### Step 6: Test Gate

After completing each task, if test runner was discovered in Step 3:

1. Run all existing tests using discovered test command.
2. **If all tests pass**: Continue to marking task complete.
3. **If any tests fail**:
 - Do **not** mark task complete.
 - Do **not** proceed to next task.
 - Fix failing test or code causing failure.
 - Re-run tests until all pass.
 - If fix is non-trivial, explain issue and approach before proceeding.

If no tests are present in repository, skip this step silently.

### Step 7: Completion Validation

When all tasks in `tasks.md` are marked `[x]`:

1. **Cross-check against spec.md**: Verify that every user story's acceptance criteria has been addressed. Note any gaps.

2. **Cross-check against plan.md**: Verify that implemented project structure matches plan.

3. **Run full test suite** (if tests exist): Confirm no regressions.

4. **Report final status**:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ IMPLEMENTATION COMPLETE

 Feature: <slug>
 Tasks: N/N complete

 User Stories:
 ├── US1 (P1): ✓ <Title>
 ├── US2 (P2): ✓ <Title>
 └── US3 (P3): ✓ <Title>

 Tests: ✓ All passing (or "No tests found")

 Spec acceptance criteria: N/N addressed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If any acceptance criteria are unaddressed, list them explicitly with recommendation.

### Step 8: Handle Errors and Blockers

If task cannot be completed:

1. **Do not skip it** — record blocker.
2. **Report clearly**:
 ```
 ❌ BLOCKED: T<NNN> — <reason>
 Impact: <which subsequent tasks are blocked>
 Suggested resolution: <what information or action is needed>
 ```
3. **Pause execution** and wait for user input before continuing.

If spec, plan, or tasks are ambiguous about what to build:
- Use `plan.md` as authority on structure and technology choices
- Use `spec.md` as authority on behavior and acceptance criteria
- If both are ambiguous, ask user before proceeding (do not guess on behavioral decisions)

## Output Format

Produces:
- Modified source files matching feature's tech stack and architecture
- Updated `tasks.md` with completed tasks marked `[x]`
- Progress reports after each task (`✓ T<NNN> — <description>`)
- Phase checkpoint summaries (`🏁 Checkpoint: <Phase> complete`)
- Final completion report when all tasks are done

## Constraints

- **ALWAYS** read `plan.md` before creating any file — use its project structure as source of truth for all paths
- **ALWAYS** mark tasks `[x]` in `tasks.md` immediately after completion
- **NEVER** create files at paths not defined in `plan.md` unless task explicitly specifies different path
- **NEVER** skip task without blocking and reporting
- **NEVER** mark task complete if tests are present and failing
- If resuming previous run, respect already-completed `[x]` tasks and do not re-execute them
- Commit messages (if committing) should reference task ID: `T<NNN>: <brief description>`
