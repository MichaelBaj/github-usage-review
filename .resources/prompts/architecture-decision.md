---
id: "architecture-decision"
version: "1.0.0"
tags: [architecture, documentation, process]
---

# Architecture Decision Record

## Context

Used when documenting significant technical decisions. ADRs capture the context, reasoning, and consequences of architectural choices so future teams understand *why* decisions were made.

## Format

```markdown
# ADR-NNNN: <Decision Title>

## Status

[Proposed | Accepted | Deprecated | Superseded by ADR-NNNN]

## Date

YYYY-MM-DD

## Context

<!-- What is the issue? What forces are at play? Why is a decision needed now? -->

## Decision

<!-- What was decided. State clearly and concisely. Use "We will..." -->

## Consequences

### Positive
<!-- Benefits of this decision -->

### Negative
<!-- Costs, tradeoffs, or risks accepted -->

### Neutral
<!-- Side effects that are neither positive nor negative -->

## Alternatives Considered

### Alternative 1: <Name>
- **Description:** What this option entails
- **Pros:** Benefits
- **Cons:** Drawbacks
- **Why rejected:** Specific reason

### Alternative 2: <Name>
- **Description:** ...
- **Pros:** ...
- **Cons:** ...
- **Why rejected:** ...
```

## Examples

```markdown
# ADR-0005: Use YAML for resource manifests

## Status
Accepted

## Date
2025-01-15

## Context
We need a configuration format for the resource manifest that maps
skills, agents, and prompts to their metadata. The format must support
comments (for documentation), be human-readable, and have broad tooling
support across Python, JavaScript, and Go.

## Decision
We will use YAML as the manifest format, parsed with PyYAML's
`safe_load` in Python tooling.

## Consequences

### Positive
- Human-readable with comment support
- Widely adopted with mature parsers in all target languages
- Supports complex nested structures naturally

### Negative
- Whitespace-sensitive — indentation errors are common
- Multiple valid syntaxes for the same structure (flow vs block)
- No native schema validation (requires external tooling)

### Neutral
- Team already familiar with YAML from CI/CD configs

## Alternatives Considered

### Alternative 1: JSON
- **Description:** Standard JSON files for manifest
- **Pros:** Strict parsing, universal support, schema validation via JSON Schema
- **Cons:** No comments, verbose for nested structures, poor human editability
- **Why rejected:** No comment support makes manifests harder to maintain

### Alternative 2: TOML
- **Description:** TOML configuration files
- **Pros:** Human-friendly, explicit types, growing adoption
- **Cons:** Nested structures are awkward, less team familiarity
- **Why rejected:** Nested resource definitions would be verbose and unfamiliar
```

## Constraints

- ADR numbers are sequential and never reused
- ADRs are immutable once Accepted — supersede with a new ADR, never edit
- Status must be one of: Proposed, Accepted, Deprecated, Superseded
- Context must explain *why now* — what triggered the need for a decision
- At least 2 alternatives must be considered and documented
- Decision must use "We will..." language for clarity
