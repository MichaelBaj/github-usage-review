---
id: "documentation-standards"
version: "1.0.0"
tags: [documentation, standards]
applies-to: "**/*.md"
---

# Documentation Standards

## Description

Standards for README structure, inline documentation, API docs, Architecture Decision Records (ADRs), and changelogs. Ensures documentation is discoverable, maintainable, and useful.

## Core Rules

1. **README Structure** — Every project README must include: project name, one-line description, prerequisites, installation, quick start, usage examples, configuration, contributing guide link, license.
2. **Inline Documentation** — Document *why*, not *what*. Code should be self-documenting for *what*. Comments explain non-obvious decisions, workarounds, and business logic rationale.
3. **API Documentation** — Every public API endpoint/function documents: purpose, parameters (name, type, required/optional, constraints), return type, error cases, and at least one usage example.
4. **ADR Format** — Use numbered ADRs (`0001-decision-title.md`) with sections: Status, Context, Decision, Consequences, Alternatives Considered. ADRs are immutable once accepted — supersede with new ADR, don't edit.
5. **Changelog** — Follow Keep a Changelog format. Sections: Added, Changed, Deprecated, Removed, Fixed, Security. Link each entry to PR or issue. Unreleased section at top.
6. **File Naming** — Lowercase kebab-case for all documentation files. Use descriptive names that indicate content scope.
7. **Links** — Use relative paths for internal links. Verify links resolve. Avoid bare URLs — use descriptive link text.
8. **Diagrams** — Use Mermaid for architecture and flow diagrams. Keep diagrams in the same file or adjacent to the text they illustrate.
9. **Versioned Docs** — Documentation changes ship with the code they describe. Never merge code without updating affected docs.
10. **Staleness** — Add `Last reviewed: YYYY-MM-DD` to long-lived docs. Review quarterly. Delete docs for removed features.

## Examples

### ✅ Correct

```markdown
# my-tool

One-line description of what this tool does.

## Prerequisites

- Python 3.11+
- uv package manager

## Quick Start

\`\`\`bash
uv run my-tool --input data.json
\`\`\`

## Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `timeout` | int | 30 | Request timeout in seconds |
```

```markdown
<!-- ADR Example -->
# ADR-0003: Use YAML for manifest format

## Status
Accepted

## Context
Need a human-readable, comment-friendly config format for resource manifests.

## Decision
Use YAML over JSON or TOML.

## Consequences
- Positive: Human-readable, supports comments, widely tooled
- Negative: Whitespace-sensitive, multiple valid syntaxes for same structure

## Alternatives Considered
- JSON: No comments, verbose
- TOML: Less familiar to team, nested structure awkward
```

### ❌ Avoid

```markdown
<!-- Missing structure, no quick start, no prereqs -->
# my-tool
This is a tool. Run it to do stuff. See code for details.
```

```markdown
<!-- Comment explaining what, not why -->
# Increment the counter
counter += 1
```

## References

- [Keep a Changelog](https://keepachangelog.com/)
- [ADR GitHub Organization](https://adr.github.io/)
- [Diátaxis Documentation Framework](https://diataxis.fr/)
