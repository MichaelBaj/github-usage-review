---
id: "commit-message"
version: "1.0.0"
tags: [git, conventions, formatting]
---

# Commit Message

## Context

Used when composing git commit messages. Enforces Conventional Commits format for consistent, parseable commit history that supports automated changelogs and semantic versioning.

## Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Type (required)

| Type | When to use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace (no logic change) |
| `refactor` | Code restructuring (no feature/fix) |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `build` | Build system, dependencies |
| `ci` | CI/CD configuration |
| `chore` | Maintenance, tooling |
| `revert` | Reverting a previous commit |

### Scope (optional)

Lowercase noun identifying the affected module, component, or area. Examples: `auth`, `parser`, `api`, `skills`, `manifest`.

### Subject (required)

- Imperative mood: "add" not "added" or "adds"
- Lowercase first letter
- No period at end
- Maximum 50 characters

### Body (optional)

- Wrap at 72 characters
- Explain *what* and *why*, not *how*
- Separate from subject with blank line

### Footer (optional)

- `BREAKING CHANGE: <description>` — for breaking API changes
- `Refs: #123` — issue/PR references
- `Co-authored-by: Name <email>` — co-author attribution

## Examples

```
feat(auth): add JWT token refresh endpoint

Tokens now auto-refresh 5 minutes before expiry. Refresh uses
rotating refresh tokens with one-time use enforcement.

Refs: #142
```

```
fix(parser): handle empty YAML frontmatter without crash

Previously, files with `---\n---` (empty frontmatter) caused a
None dereference in parse_frontmatter(). Now returns empty dict.
```

```
refactor(skills): extract frontmatter parsing to shared module

BREAKING CHANGE: parse_frontmatter() moved from skills.utils to
shared.frontmatter. Update imports accordingly.
```

## Constraints

- Subject line ≤ 50 characters
- Body lines ≤ 72 characters
- One logical change per commit
- Never mix formatting changes with logic changes
- `BREAKING CHANGE` footer is required for any backward-incompatible change
