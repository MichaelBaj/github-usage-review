# Planner Templates and Format Examples

Selective-load reference for `ai-keel.planner` agent. Contains effort estimation formats, risk management formats, and plan versioning YAML templates.

---

## Effort Estimation — Phase File Format

```
## Effort Estimate (Agentic)
- Tasks: 6 (3 quick, 2 standard, 1 deep)
- Agent wall-clock: ~55 min
- Human review gates: ~15 min (one gate at end of phase)
- With buffer (20%): ~66 min agent / ~15 min human
- Confidence: Medium — MCP tool wiring adds uncertainty
```

## Effort Estimation — Overview File Format

```
## Effort Summary (Agentic)
| Phase | Agent Wall-Clock | Human Review | Buffered Agent | Confidence |
|-------|-----------------|--------------|----------------|------------|
| 01 — Scaffolding | 20 min | 10 min | 24 min | High |
| 02 — Core Logic | 45 min | 15 min | 54 min | Medium |
| 03 — Integration | 30 min | 10 min | 36 min | Low |
| **Total** | **95 min** | **35 min** | **~2 hrs agent** | |
```

---

## Risk Management — Phase File Format

```
## Risks
- **[Technical]** tshark version mismatch may break PCAP parsing → pin version in prerequisites
- **[Scope]** User may request additional output formats mid-phase → define format list upfront
- **[Knowledge]** New SSR log format unfamiliar → allocate spike time early
```

## Risk Management — Overview File Format

```
## Top Risks
- **[Technical]** tshark version mismatch (Phase 02) → pin version
- **[Knowledge]** New log format unfamiliar (Phase 02) → spike task allocated
- **[Integration]** MCP tool ↔ script contract undefined (Phase 03) → define interface in Phase 01
```

---

## Plan Versioning — YAML Header Template

```yaml
---
plan: <plan-name>
phase: <phase-number-and-name> (or "overview" for 00-overview.md)
category: new-code | refactor | research
status: draft | reviewed | approved | in-progress | complete
created: YYYY-MM-DD
last-updated: YYYY-MM-DD
estimated-hours: <number>
---
```

## Plan Versioning — Revision Log Template

```
## Revision Log
| Date | Author | Change |
|------|--------|--------|
| YYYY-MM-DD | agent | Initial draft generated |
```
