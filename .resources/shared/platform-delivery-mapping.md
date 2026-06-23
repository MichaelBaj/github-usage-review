# Platform Delivery Mapping

Working design document: for each resource × platform, what native mechanism delivers it.

---

## Skills Delivery

| Skill | Copilot | Claude |
|-------|---------|--------|
| caveman | injected into copilot-instructions.md | inline CLAUDE.md |
| ref-convention | injected into copilot-instructions.md | inline CLAUDE.md |
| shell-safety | injected into copilot-instructions.md | inline CLAUDE.md |
| caveman-commit | skill (description) | .claude/skills/ |
| caveman-compress | skill (description) | .claude/skills/ |
| python-coding-standards | instruction (applyTo: **/*.py) | .claude/skills/ |
| security-review | instruction (applyTo: **/*.{js,ts,py,go}) | .claude/skills/ |
| code-review | skill (description) | .claude/skills/ |
| documentation-standards | instruction (applyTo: **/*.md) | .claude/skills/ |
| testing-standards | instruction (applyTo: **/test_*) | .claude/skills/ |
| mermaid-diagrams | skill (description) | .claude/skills/ |

---

## Agents Delivery

Agents = complex workflows triggered by task context. Auto-invoke mechanisms.
NOTE: Custom agent **personas** (named identity + tool restriction) are Copilot-only.

| Agent | Copilot | Claude |
|-------|---------|--------|
| planning-agent | .agent.md | .claude/skills/planning/SKILL.md |
| specwip.plan | .agent.md | .claude/skills/planning/SKILL.md |
| designer | .agent.md | .claude/skills/designer/SKILL.md |
| code-review-agent | .agent.md | .claude/skills/code-review-agent/SKILL.md |
| refactoring-agent | .agent.md | .claude/skills/refactoring/SKILL.md |
| security-review-agent | .agent.md | .claude/skills/security-review-agent/SKILL.md |

---

## Prompts Delivery

Prompts = user-invoked templates/commands. Explicit invocation mechanisms.

| Prompt | Copilot | Claude |
|--------|---------|--------|
| commit-message | .prompt.md | .claude/commands/commit-message.md |
| pr-description | .prompt.md | .claude/commands/pr-description.md |
| architecture-decision | .prompt.md | .claude/commands/architecture-decision.md |
| repo-architecture-review | .prompt.md | .claude/commands/repo-architecture-review.md |

---

## Always-On Delivery Strategy

| Content | Global-File Platforms (Copilot, Claude) |
|---------|----------------------------------------|
| ref-convention | Injector CLI → section in global file |
| caveman | Injector CLI → section in global file |
| shell-safety | Injector CLI → section in global file |

**Language requirement:** Always-on content MUST use assertive, imperative language ("You MUST", "NEVER", "NOT optional"). Weak phrasing ignored by agents.

---

## Per-Platform File Format Templates

### Copilot Skill (SKILL.md)

```yaml
---
name: skill-name
description: >
  Trigger-rich description for auto-invoke.
  Include keywords that match when user task is relevant.
context: fork              # optional — run in subagent, return only result
---
@ref[.resources/skills/skill-name.md]
```

### Copilot Instruction

```yaml
---
applyTo: "**/*.py"         # glob pattern for file-scoped activation
excludeAgent: "code-review" # optional — exclude from specific agent contexts
---
@ref[.resources/skills/skill-name.md]
```

### Copilot Agent

```yaml
---
name: Agent Name
description: When to invoke this agent
tools: [read, search, edit]  # tool allowlist
model: claude-4.7-sonnet     # optional model override
handoff: next-agent-name     # optional agent chaining
---
@ref[.resources/agents/agent-name.md]
```

NOTE: Custom agent personas are **Copilot-only**. No equivalent in other platforms.

### Claude Skill (SKILL.md)

```yaml
---
name: skill-name
description: >
  Trigger-rich description for model-decision loading.
  Include keywords that match when user task is relevant.
disable-model-invocation: true  # optional — user-only
user-invocable: false           # optional — model-only
---
@ref[.resources/skills/skill-name.md]
```

### Minimal CLAUDE.md (Consumer Base)

```markdown
# File Reference Convention (MANDATORY)
You MUST follow this convention — it is NOT optional.
When you encounter `@ref[path]` in ANY file, you MUST immediately call read_file on the bracketed path. Do NOT skip, summarize, or guess. Do NOT pre-load — load ONLY when encountered.

# Caveman Mode (ALWAYS ON — NO EXCEPTIONS)
You MUST apply caveman-full to ALL responses (except code blocks, commit messages, PR content, reports, plan/design docs).
Rules: Drop articles, filler, pleasantries, hedging. Fragments OK. Technical terms exact.
Pattern: [thing] [action] [reason]. OFF only when user says "stop caveman". Violation = broken output.

# Shell Safety
NEVER use heredoc (<<EOF) in terminal commands. Use file writing tools instead. No exceptions.
```
