---
id: "pr-description"
version: "1.0.0"
tags: [git, review, formatting]
---

# PR Description

## Context

Used when creating pull request descriptions. Provides reviewers with sufficient context to understand the change, its motivation, and how to verify it.

## Format

```markdown
## Summary

<!-- One paragraph: what this PR does and why -->

## Motivation

<!-- Why this change is needed. Link to issue/ticket if applicable. -->

## Changes

<!-- Bullet list of concrete changes, grouped by area -->

- **area**: description of change

## Testing

<!-- How was this tested? Include commands, screenshots, or test output. -->

- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Breaking Changes

<!-- List any backward-incompatible changes. Omit section if none. -->

None

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests cover new/changed behavior
- [ ] No secrets or credentials committed
```

## Examples

```markdown
## Summary

Add YAML frontmatter validation for all resource files. Ensures every
skill, agent, and prompt has required fields (id, version, tags) before
merge.

## Motivation

Invalid frontmatter caused runtime errors in the manifest sync pipeline.
Catching these at PR time prevents broken deployments. Fixes #87.

## Changes

- **scripts**: add `validate_frontmatter.py` with YAML parsing and field checks
- **tests**: add `test_frontmatter.py` covering valid, missing, and malformed cases
- **ci**: add frontmatter validation step to PR workflow

## Testing

- `uv run pytest tests/test_frontmatter.py -v` — 12 tests pass
- Manually tested with intentionally broken frontmatter files

## Breaking Changes

None

## Checklist

- [x] Code follows project style guidelines
- [x] Self-review completed
- [x] Documentation updated
- [x] Tests cover new/changed behavior
- [x] No secrets or credentials committed
```

## Constraints

- Summary must be one paragraph, not a bullet list
- Changes section must use bullet list grouped by area
- Testing section must include concrete verification steps
- Breaking Changes section required even if "None"
- Checklist items must all be addressed before requesting review
