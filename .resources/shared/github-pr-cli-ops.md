# GitHub PR — CLI Operations

CLI/GraphQL-path implementations. Load **only** when `MCP_AVAILABLE = false`.
MCP path: [github-pr-mcp-ops.md](.resources/shared/github-pr-mcp-ops.md).

---

## Fetch PR Diff / Files

```bash
gh pr diff PR_NUMBER
```

Structured file list only:

```bash
gh pr view PR_NUMBER --json files -q '.files[].path'
```

---

## Fetch PR Review Comments

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 10) {
            nodes {
              id
              databaseId
              author { login }
              body
              path
              line
              originalLine
              originalStartLine
              diffHunk
            }
          }
        }
      }
    }
  }
}' -f owner="OWNER" -f repo="REPO" -F pr=PR_NUMBER
```

> **ID for replies:** Use `databaseId` (integer) as `COMMENT_ID` in REST reply call below. GraphQL `id` field won't work with REST API — no second lookup needed.

---

## Post Reply to PR Comment

```bash
gh api --method POST \
  "/repos/OWNER/REPO/pulls/PR_NUMBER/comments/COMMENT_ID/replies" \
  -f body="MESSAGE"
```

`COMMENT_ID` = integer `databaseId` from **Fetch PR Review Comments**.

---

## Verify and Check Out PR Branch

```bash
gh pr view PR_NUMBER --json headRefName -q '.headRefName'
```

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
