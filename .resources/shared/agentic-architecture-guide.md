# Agentic Architecture Guide

## Purpose

Source of truth for structuring repo AI agent artifacts across platforms (Copilot, Claude). Mechanism definitions, placement rules, anti-bloat rules, platform-native delivery model.

> External anchors (read once, do not restate here):
> - Context-engineering rationale: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - LLM security baseline: https://owasp.org/www-project-top-10-for-large-language-model-applications/

---

## Core Principles

1. **Separation of concerns** — each mechanism has distinct role; avoid duplication across layers.
2. **Minimize always-on context** — only broadly relevant content loads on every interaction.
3. **Load specialization on demand** — skills for deep domain knowledge, loaded by relevance.
4. **Platform-native delivery** — use each platform's native lazy-loading; never monolithic @ref lists.
5. **Measure context cost explicitly** — evaluate by load scope, volatility, utility; not prose quality.
6. **Platform-agnostic canonical source** — define content once in `.resources/`, route to each platform's native format.

---

## Architecture Overview

### Canonical Source → Platform Routing Model

```text
.resources/skills/*.md        ← single source of truth (platform-agnostic)
.resources/agents/*.md        ← single source of truth
.resources/prompts/*.md       ← single source of truth
        │
        ├─→ routing/copilot/    (skills/, instructions/, agents/, prompts/)
        └─→ routing/claude/     (CLAUDE.md + .claude/skills/ + .claude/commands/)
```

Each routing target uses the platform's **native file structure and trigger mechanism**. No monolithic files listing all resources.

---

## Platform Mechanisms — 8 Artifact Categories

### Category 1: Always-On Instructions

Content loads on EVERY interaction. Keep minimal.

| Platform | Mechanism | Path | Format |
|----------|-----------|------|--------|
| **Copilot** | Global instructions file | `.github/copilot-instructions.md` | Markdown (injected sections) |
| **Claude** | Root config file | `CLAUDE.md` | Markdown (injected sections) |

**Delivery model:**
- Copilot/Claude: Injector CLI injects sections into existing global file

**What belongs here:** ref-convention, caveman mode, shell safety. Nothing else.

---

### Category 2: Scoped/Glob Rules

Instructions that activate only for specific file types or directories.

| Platform | Mechanism | Trigger | Example |
|----------|-----------|---------|---------|
| **Copilot** | Instructions file | `applyTo: "**/*.py"` in frontmatter | `.github/instructions/python.instructions.md` |
| **Claude** | Skill with glob description | Description mentioning file types (model-inferred) | `.claude/skills/python/SKILL.md` |

**What belongs here:** python-coding-standards, security-review, documentation-standards, testing-standards.

---

### Category 3: Reusable Prompt Templates

User-invoked commands/templates for repeated tasks.

| Platform | Mechanism | Invocation | Path |
|----------|-----------|-----------|------|
| **Copilot** | Prompt file | Slash command in chat | `.github/prompts/*.prompt.md` |
| **Claude** | Command file | `/command-name` | `.claude/commands/*.md` |

**What belongs here:** commit-message, pr-description, architecture-decision, repo-architecture-review.

---

### Category 4: Custom Agent Personas

Named identity + tool restriction + handoff chains. **Copilot-only native concept.**

| Platform | Mechanism | Notes |
|----------|-----------|-------|
| **Copilot** | `.github/agents/*.agent.md` | Full persona: name, tools, instructions, handoff |
| **Claude** | Skill (auto-invoke by description) | No true persona — approximated via skill descriptions |

**Key insight:** Agent persona (identity + tool restriction) exists only in Copilot. Other platforms receive workflow logic via skill/rule mechanism. Agent `description` drives auto-invoke.

---

### Category 5: Agent Skills (On-Demand Specialization)

Deep knowledge loaded by relevance, not always-on.

| Platform | Mechanism | Trigger | Key Fields |
|----------|-----------|---------|------------|
| **Copilot** | Skill directory | Description match (3-stage) | `context: fork` (subagent isolation) |
| **Claude** | Skill directory (3-stage) | Description match (auto-invoke) | `disable-model-invocation`, `user-invocable` |

**3-stage loading (Copilot/Claude):**
1. Description only → platform decides relevance
2. SKILL.md header loaded if relevant
3. Full content + @ref targets loaded if activated

**What belongs here:** caveman-commit, caveman-compress, code-review, mermaid-diagrams + all agent workflows.

---

### Category 6: Lifecycle Hooks

Pre/post task automation. Limited cross-platform support.

| Platform | Mechanism | Path |
|----------|-----------|------|
| **Copilot** | Hook JSON files | `.github/hooks/*.json` |
| **Claude** | Settings file | `.claude/settings.json` |

**Not currently routed by ai-keel.** Future consideration.

---

### Category 7: Ephemeral Memory

Agent-managed notes. Platform-specific, not routable.

| Platform | Mechanism | Notes |
|----------|-----------|-------|
| **Copilot** | Memory tool (`/memories/`) | Scoped: user, session, repo |
| **Claude** | No native memory | — |

**Not managed by ai-keel.** Platform-native only.

---

### Category 8: MCP Server Configuration

Tool server connections. Handled by `mcp_merge.py`.

| Platform | Config Path |
|----------|------------|
| **Copilot** | `.vscode/mcp.json` or `.github/copilot/mcp.json` |
| **Claude** | `.claude/mcp.json` |

---

## Platform-Specific Fields Reference

### Copilot

| Field | Context | Effect |
|-------|---------|--------|
| `context: fork` | Skills | Run in subagent, return only result (reduces context pollution) |
| `excludeAgent: "name"` | Instructions | Don't apply when this agent is active |
| `applyTo: "glob"` | Instructions | File-scoped activation |
| `handoff:` | Agents | Chain to next agent on completion |

### Claude

| Field | Context | Effect |
|-------|---------|--------|
| `disable-model-invocation: true` | Skills | User-only invocation (model cannot auto-invoke) |
| `user-invocable: false` | Skills | Model-only (hidden from user) |
| 3-stage loading | Skills | Description → header → full content |

---

## Design Principles for Multi-Platform Delivery

1. **Canonical source is platform-agnostic.** `.resources/` content has no platform-specific frontmatter.
2. **Routing adds platform-native wrappers.** Each `routing/{platform}/` file adds correct frontmatter/structure.
3. **Always-on = injected.** Global-file platforms (Copilot, Claude) inject into existing root instruction files.
4. **Skills use native lazy-loading.** Never list all skills in global file. Platform description-matching handles discovery.
5. **Agents become skills/rules outside Copilot.** True persona is Copilot-only. Other platforms get workflow via skill/rule mechanism.
6. **Prompts map to user-invoked mechanisms.** Copilot slash commands and Claude /commands.

---

## Context Efficiency Lens

| Load scope | Examples | Review question |
|---|---|---|
| **Always-on** | ref-convention, caveman, shell-safety | Does this deserve to tax every conversation? |
| **File-scoped** | python-standards on *.py files | Is glob narrow enough? |
| **On-demand (skill)** | code-review, mermaid-diagrams | Description trigger-rich? Minimal overlap with other skills? |
| **User-invoked (prompt)** | commit-message, pr-description | Clear inputs/outputs? |
| **Workflow (agent)** | specwip.plan, designer | Complex enough to justify agent? |

---

## Placement Rules

| Put in… | If… |
|---|---|
| Always-on (injected/alwaysApply) | applies to ALL tasks; defines universal behavior; ≤ 3 items total |
| Scoped/glob rules | applies only to specific file types; narrow pattern |
| Skills | knowledge is deep and specialized; only relevant sometimes; trigger-dense description |
| Prompts | task is frequently repeated; needs structured invocation |
| Agent workflows | workflow is complex, multi-step, role-specific |
| Shared resources | content is large and factual; loaded on demand via @ref |

---

## Anti-Patterns

1. **Monolithic global file** — All @ref directives in one file forces eager loading of everything
2. **Skills as dumping grounds** — Skills containing general rules from root instructions
3. **Agent sprawl** — More than ~6 agents, or agents with overlapping scopes
4. **Always-on bloat** — More than 3 always-on items (ref-convention + caveman + shell-safety)
5. **Lazy-load bypass** — Large templates copied into always-loaded files instead of shared resources
6. **Weak always-on language** — Using suggestions ("when you see") instead of mandates ("You MUST") for critical behaviors
7. **Cross-file contract drift** — Different files restating same rule with different constraints
8. **Platform-specific content in canonical source** — Frontmatter or triggers in `.resources/` files
9. **Duplicate delivery** — Same content delivered as both injected section AND separate rule file
10. **Excessive trigger-word overlap** — Multiple skills firing on same requests due to undifferentiated descriptions

---

## Evaluation Checklist

**Always-on content:** ≤ 3 sections; assertive language ("MUST", "NEVER"); each universally applicable.

**Skills:** clearly scoped; truly specialized; no global rules; trigger-dense descriptions; minimal trigger overlap.

**Prompts:** clear inputs/outputs; recurring tasks; user-invoked only.

**Agents:** each serves real role; limited count (≤ 6); Copilot gets full persona, others get skill/rule equivalent.

**Routing:** every platform uses native mechanism; no monolithic @ref lists; routing adds only platform wrapper.

**Context efficiency:** load scope classified; always-on minimized; pointer + read replaces inline bulk.
