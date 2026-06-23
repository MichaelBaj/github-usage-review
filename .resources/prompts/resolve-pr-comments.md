---
id: "resolve-pr-comments"
version: "1.0.0"
tags: [git, review, automation, github, pr]
---

# Resolve PR Review Comments

> **Agent instructions:** Execute every bash command block directly via terminal tool. Do NOT print commands for user to run — run them yourself, report results.
>
> **No terminal access?** Stop immediately. Tell user:
> "I don't have permission to run terminal commands. Click the **wrench icon** (Tools) in chat toolbar, enable **Terminal (run_in_terminal)**, resend your message."
> Do not proceed until terminal access confirmed.

## Inputs

- PR number (optional): `${input:prRef:PR number (e.g. 42)}`; if blank, auto-detect from current branch:
  - **MCP path:** `list_pull_requests` filtered by `head` = current branch.
  - **CLI fallback:** `gh pr view --json number -q '.number'`
  - If auto-detection fails, stop and ask user for PR number.
- Author filter (optional): `${input:authorFilter:Filter by comment author — e.g. "copilot" for Copilot-only, a username, or leave blank for ALL unresolved comments}`
- Test command: `${input:testCmd:Command to run tests — leave blank to auto-detect (e.g. pytest, npm test, make test)}`

---

## Phase 1 — Identity, MCP Detection, and Routing

Follow all three steps in @ref[.resources/shared/github-pr-methods.md]:
1. **Resolve PR Identity** — full URL → extract `OWNER`, `REPO`, `PR_NUMBER` from path. Number only → infer `OWNER`/`REPO` from git remote. Blank → infer from remote AND auto-detect `PR_NUMBER` from current branch (MCP: `list_pull_requests` filtered by `head`; CLI: `gh pr view --json number -q '.number'`). Stop with error if `PR_NUMBER` unresolvable.
2. **Determine MCP Availability** — set `MCP_AVAILABLE`.
3. **Load Operations File** — read `github-pr-mcp-ops.md` or `github-pr-cli-ops.md` based on `MCP_AVAILABLE`. Do NOT load both.

Then follow **Verify and Check Out PR Branch** from loaded ops file.

Report resolved `OWNER`, `REPO`, `PR_NUMBER`, `MCP_AVAILABLE`, and current branch before continuing. Do not proceed on wrong branch.

---

## Phase 2 — Fetch Unresolved Review Threads

Use **Fetch PR Review Comments** from loaded ops file to retrieve all review threads.

### Filtering Logic

Keep threads that are **unresolved**:
- `isResolved` is `false` (CLI path), OR
- No non-bot reply exists in chain (MCP path, check `in_reply_to_id`).

Apply **author filter** based on `${input:authorFilter:authorFilter}`:

| `authorFilter` value | Behavior |
|---|---|
| blank / empty | Keep **all** unresolved threads regardless of author |
| `copilot` | Keep threads where top-level comment author contains `copilot` (case-insensitive), or is `github-advanced-security[bot]`, or `github-actions[bot]` with Copilot suggestion signature |
| any other value | Keep threads where top-level comment author matches value (case-insensitive substring) |

Report:
- Data source: MCP or GraphQL.
- Total review threads / top-level comments on PR.
- Unresolved threads matching filter.
- Per matching thread: file path, line number, author, comment body (first 300 chars), comment ID for Phase 6 replies (string `id` for MCP; integer `databaseId` for CLI — both from single fetch, no second lookup).
- **If none found:** report "No unresolved review comments matching filter on PR #N. Nothing to fix." Stop.

---

## Phase 3 — Plan and Confirm Fixes (Interactive)

Work through every unresolved thread from Phase 2.

### 3a — Propose Action Plan

Per thread:
1. Read file at `path` via file-reading tool. Context around `line` (±20 lines).
2. Interpret review comment — security, code smell, logic error, style, missing test, etc.
3. Determine recommended action: **fix**, **skip** (ambiguous/contradictory), or **discuss** (needs clarification).

Present full action plan as numbered table:

| # | File | Line | Author | Issue summary | Recommendation | Proposed fix (brief) |
|---|------|------|--------|---------------|----------------|---------------------|
| 1 | `src/foo.py` | 42 | copilot | Unused import | ✅ Fix | Remove `import os` |
| 2 | `src/bar.py` | 17 | copilot | Ambiguous advice | ⚠️ Skip | — |
| 3 | `src/baz.py` | 88 | reviewer | Missing null check | ✅ Fix | Add guard clause |

Ask user to confirm, modify, or skip items. Wait for response before proceeding.

Accepted responses:
- **"looks good"** / **"go"** / **"proceed"** → apply all recommended fixes.
- **Numbered adjustments** (e.g., "skip #3, fix #2 differently: use X instead") → update plan.
- **"skip all"** → stop, report nothing to fix.

### 3b — Apply Confirmed Fixes

After user confirmation, apply fixes for ✅ items:
1. Apply **minimal correct fix**. No refactoring beyond what comment requests.
2. If comment has ` ```suggestion ``` ` block, apply that exact change unless user overrode.
3. ⚠️ Skip items: do nothing, record reason.

Update fix table with actual status:

| # | Thread ID | File | Line | Issue summary | Fix applied | Status |
|---|-----------|------|------|---------------|-------------|--------|
| 1 | `abc123`  | `src/foo.py` | 42 | Unused import | Removed `import os` | ✅ Fixed |
| 2 | `def456`  | `src/bar.py` | 17 | Ambiguous — conflicting advice | — | ⚠️ Skipped |

Record comment ID for every fixed thread — required in Phase 6.

---

## Phase 4 — Baseline Test Check

If `${input:testCmd:testCmd}` provided, use it. Otherwise auto-detect:
```bash
ls pytest.ini pyproject.toml setup.cfg Makefile package.json 2>/dev/null | head -10
```

Run test command and capture result. Python projects:
```bash
python -m pytest --tb=short -q 2>&1 | tail -40
```

Report: pass count, fail count, failing test names. If tests already failing before your changes, note explicitly — use `git stash && <test-command> && git stash pop` to confirm.

Fix any test failure **caused by your changes** before Phase 5. Re-run after each fix. Do not proceed until previously-passing tests pass again.

---

## Phase 5 — Commit Changes

```bash
git add -A
git status
```

Commit referencing PR with fix list:
```bash
git commit -m "fix: address review comments (PR #PR_NUMBER)

- <one bullet per fix from Phase 3 table>"
```

Report: commit hash (`git log -1 --oneline`) and full changed file list.

---

## Phase 6 — Reply to Each PR Comment Thread

For every ✅ Fixed thread, post reply via **Post Reply to PR Comment** from loaded ops file. Body: `"Fixed in commit COMMIT_HASH: BRIEF_DESCRIPTION"`.

Report per reply: method (MCP/CLI), comment ID, success/failure. Flag failed replies with error body.

For ⚠️ Skipped threads, do NOT reply — leave open for human review.

---

## Phase 7 — Resolve Fixed Threads

For every ✅ Fixed thread, mark it resolved via GraphQL mutation using the thread node ID (`id` field from **Fetch PR Review Comments** — the string like `PRRT_kwDO...`, NOT `databaseId`):

```bash
gh api graphql -f query='
mutation {
  resolveReviewThread(input: {threadId: "THREAD_NODE_ID"}) {
    thread { id isResolved }
  }
}'
```

Run one mutation per thread. Confirm `isResolved: true` in response before continuing.

For ⚠️ Skipped threads, do NOT resolve — leave open for human review.

Report per thread: thread node ID, `isResolved` from response, success/failure.

---

## Output Contract

Final summary:

**PR:** `https://github.com/OWNER/REPO/pull/PR_NUMBER`
**Commit:** `COMMIT_HASH` — `fix: address review comments (PR #N)`

| Metric | Value |
|---|---|
| Unresolved threads found (matching filter) | N |
| Fixed and replied | N |
| Resolved (GitHub thread marked resolved) | N |
| Skipped (ambiguous) | N |
| Tests passing before / after | X → Y |
| Files modified | list |

**Skipped threads** (for human follow-up):

| Thread ID | File | Line | Reason skipped |
|---|---|---|---|
| … | … | … | … |
