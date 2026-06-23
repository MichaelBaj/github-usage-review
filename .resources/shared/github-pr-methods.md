# GitHub PR — Shared Methods

Entry point for any prompt operating on a GitHub PR. Covers identity resolution, MCP detection, routes to appropriate ops file.

---

## Step 1 — Resolve PR Identity

Parse PR reference:

- **Full URL** (`https://github.com/owner/repo/pull/42`) — extract `OWNER`, `REPO`, `PR_NUMBER` from path segments.
- **Number only** — infer `OWNER`/`REPO` from git remote:

```bash
git remote get-url origin
```

SSH remotes (`git@github.com:owner/repo.git`) → strip `git@github.com:` prefix and `.git` suffix.
HTTPS remotes (`https://github.com/owner/repo.git`) → strip `https://github.com/` and `.git`.

Report resolved `OWNER`, `REPO`, `PR_NUMBER` before continuing.

---

## Step 2 — Determine MCP Availability

Call `mcp_io_github_git_get_me`. Valid user object → `MCP_AVAILABLE = true`. Otherwise → `MCP_AVAILABLE = false`.

Any MCP exception or unusable result = unavailable (tool missing, auth failure, network failure, timeout, invalid response). Set `MCP_AVAILABLE = false`.

---

## Step 3 — Load Operations File (do this now)

| `MCP_AVAILABLE` | Action |
|---|---|
| `true` | Read [github-pr-mcp-ops.md](.resources/shared/github-pr-mcp-ops.md) — use for all PR operations. Do NOT load CLI ops. |
| `false` | Read [github-pr-cli-ops.md](.resources/shared/github-pr-cli-ops.md) — use for all PR operations. Do NOT load MCP ops. |

After loading ops file, continue with calling prompt's next phase.
