---
id: "caveman-commit"
version: "1.0.0"
tags: [communication, token-efficiency, git, commit]
applies-to: "**/*"
model: "Claude Haiku 4.5 (copilot)"
---

# Caveman Commit

## Description

Ultra-compressed commit message generator. Cuts noise from commit messages while preserving intent and reasoning. Conventional Commits format. Subject ≤50 chars, body only when "why" isn't obvious. Use when user says "write a commit", "commit message", "generate commit", "/commit", or invokes /caveman-commit. Auto-triggers when staging changes.

## Core Rules

Write commit messages terse and exact. Conventional Commits format. No fluff. Why over what.

### Subject line

- `<type>(<scope>): <imperative summary>` — `<scope>` optional
- Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `build`, `ci`, `style`, `revert`
- Imperative mood: "add", "fix", "remove" — not "added", "adds", "adding"
- ≤50 chars when possible, hard cap 72
- No trailing period
- Match project convention for capitalization after colon

### Body (only if needed)

- Skip when subject is self-explanatory
- Add body only for: non-obvious *why*, breaking changes, migration notes, linked issues
- Wrap at 72 chars
- Bullets `-` not `*`
- Reference issues/PRs at end: `Closes #42`, `Refs #17`

### Never include

- "This commit does X", "I", "we", "now", "currently" — diff says what
- "As requested by..." — use Co-authored-by trailer
- "Generated with Claude Code" or any AI attribution
- Emoji (unless project convention requires)
- Restating file name when scope already says it

## Examples

### ✅ Correct

Diff: new endpoint for user profile with body explaining the why:

```
feat(api): add GET /users/:id/profile

Mobile client needs profile data without the full user payload
to reduce LTE bandwidth on cold-launch screens.

Closes #128
```

Breaking API change:

```
feat(api)!: rename /v1/orders to /v1/checkout

BREAKING CHANGE: clients on /v1/orders must migrate to /v1/checkout
before 2026-06-01. Old route returns 410 after that date.
```

### ❌ Avoid

- "feat: add a new endpoint to get user profile information from the database"
- "This commit adds support for..."
- Using past tense ("added", "fixed")

## Auto-Clarity

Always include body for: breaking changes, security fixes, data migrations, reverts of prior commit. Never compress these to subject-only — future debuggers need context.

## Boundaries

Only generates commit message. Does not run `git commit`, stage files, or amend. Output message as code block ready to paste. "stop caveman-commit" or "normal mode": revert to verbose commit style.

## References

- [caveman](.resources/skills/caveman.md) — parent communication mode
