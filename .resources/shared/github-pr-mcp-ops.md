# GitHub PR — MCP Operations

MCP-path implementations. Load **only** when `MCP_AVAILABLE = true`.
CLI path: [github-pr-cli-ops.md](.resources/shared/github-pr-cli-ops.md).

---

## Fetch PR Diff / Files

Call `mcp_io_github_git_pull_request_read`:
- `owner`: OWNER
- `repo`: REPO
- `pullNumber`: PR_NUMBER
- `method`: `"get_files"`

Returns changed-file objects with `filename`, `patch`, `additions`, `deletions`, `status`.

---

## Fetch PR Review Comments

Call `mcp_io_github_git_pull_request_read`:
- `owner`: OWNER
- `repo`: REPO
- `pullNumber`: PR_NUMBER
- `method`: `"get_review_comments"`

Returns comment objects with `id`, `user.login`, `body`, `path`, `line`, `diff_hunk`, `in_reply_to_id`.

Comments with `in_reply_to_id` set = replies — skip when identifying top-level threads.

> **Thread resolution:** MCP returns individual comments, not pre-resolved threads. Treat each top-level comment as open thread unless non-bot reply already exists in chain (`in_reply_to_id` pointing back).

> **ID for replies:** MCP `id` = string node ID. Use `mcp_io_github_git_add_reply_to_pull_request_comment` (accepts string `id`) — no additional lookup needed.

---

## Post Reply to PR Comment

Call `mcp_io_github_git_add_reply_to_pull_request_comment`:
- `owner`: OWNER
- `repo`: REPO
- `pullNumber`: PR_NUMBER
- `commentId`: string `id` from **Fetch PR Review Comments**
- `body`: reply text

---

## Verify and Check Out PR Branch

Fetch PR head branch: call `mcp_io_github_git_pull_request_read` with `method: "get"` → use `head.ref`.

Confirm local branch matches:
```bash
git branch --show-current
```

If different:
```bash
git fetch origin
git checkout PR_BRANCH_NAME
```

If checkout fails (uncommitted changes), stop — tell user to stash or commit first.
