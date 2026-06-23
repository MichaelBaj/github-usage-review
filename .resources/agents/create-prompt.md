---
id: create-prompt
version: 1.0.0
tags: [generator, internal, authoring]
---

# keel-new-prompt

## Purpose

Scaffold a new ai-keel prompt with content, routing for all agents, and manifest entry. Invoke this agent whenever a reusable prompt template needs to be added to the repository.

Prompts appear as slash commands in Copilot Chat (type `/` to see them). Use prompts for **single focused tasks with parameterized inputs** — e.g., "generate a changelog entry for these commits", "explain this function", "write tests for this class".

> **Prompt vs Skill?** If the task is single-shot with clear inputs/outputs → Prompt. If it's a multi-step workflow with assets (scripts, reference docs) → use `keel-new-skill` instead.

## Extract from Conversation

Before asking questions, review the conversation history. If the user has been working on a repeatable task pattern (e.g., generating tests, explaining code, writing commit messages), generalize it into a reusable prompt. Extract:
- The core task being performed
- Any implicit inputs (selected code, file type, active file context)
- The desired output format or style

## Process

### 1. Gather Requirements

Ask only what you can't infer from context:
- `name` — kebab-case identifier (e.g., `summarize-pr`), no spaces, lowercase only
- `description` — what this prompt does and when to use it (see [Writing Effective Descriptions](#writing-effective-descriptions))
- `mode` — `ask` (conversational Q&A), `edit` (in-place file edits), or `agent` (full agentic with tools); default `ask`
- `context` — situational context: when is this prompt used and what does the user bring to it?
- `output-format` — required output format, structure, or length guidance
- `constraints` — formatting rules, tone, length limits, things to avoid
- `tags` — comma-separated kebab-case tags (e.g., `summarization, pr, automation`)

### 2. Create Prompt File

Copy `.resources/prompts/_TEMPLATE.md` to `.resources/prompts/{name}.md`:
- Set frontmatter: `id: {name}`, `version: 1.0.0`, `tags: [{tags}]`
- Replace `# <Prompt Name>` with `# {Title-Cased Name}`
- Fill in `## Context`, `## Constraints` from gathered requirements
- Leave `## Format` and `## Examples` for the user to complete

### 3. Create Claude Routing

Create `routing/claude/.claude/commands/{name}.md`:

```markdown
@ref[.resources/prompts/{name}.md]
```

### 4. Create Copilot Routing

Create `routing/copilot/prompts/{name}.prompt.md`:

```markdown
---
mode: {mode}
description: '{keyword-rich description — see Writing Effective Descriptions}'
---

@ref[.resources/prompts/{name}.md]
```

Prompts appear as slash commands in Copilot Chat. The `description` field controls when the agent auto-suggests the prompt and what text the user sees in the slash command list.

> Supported `mode` values:
> - `ask` — conversational; agent responds with text (default)
> - `edit` — in-place edits to files currently in context
> - `agent` — full agentic mode with tool access (file reads, terminal, etc.)

### 5. Create Cursor Routing

Create `routing/cursor/.cursor/rules/{name}.mdc`:

```yaml
---
description: "{description}"
---
@ref[.resources/prompts/{name}.md]
```

(No globs, no alwaysApply — makes it "manual" trigger in Cursor)

### 6. Create Windsurf Routing

Create `routing/windsurf/.windsurf/rules/{name}.md`:

```yaml
---
trigger: manual
description: "{description}"
---
@ref[.resources/prompts/{name}.md]
```

### 7. Add Manifest Entry

Append the following resource entry to `manifest.yml`:

```yaml
- path: prompts/{name}.md
  type: prompt
  description: "{context (first sentence, ≤200 chars)}"
  tags: [{tags}]
```

### 8. Validate

Run the following validation scripts and confirm they pass:
- `uv run scripts/validate_refs.py` — checks all `@ref` targets resolve
- `uv run scripts/validate_manifest.py` — checks manifest conforms to schema

### 9. Iterate

After creating the files:
1. Show the user the generated `description` field and suggest example invocations (e.g., `/summarize-pr this diff`)
2. Identify the most ambiguous part of the format/constraints and ask a clarifying question
3. Once finalized, summarize what was created and propose related prompts or skills to create next

## Writing Effective Descriptions

The `description` field in the `.prompt.md` file controls discoverability in Copilot Chat slash commands and on-demand loading.

**Pattern:** `"{Verb} {what it produces}. Use when {situation}. {keywords}."`

| ❌ Weak | ✅ Strong |
|---|---|
| "Summarize a PR" | "Summarize a pull request into bullet points. Use when writing a PR description, changelog entry, or release note." |
| "Write tests" | "Generate unit tests for a function or class. Use when adding test coverage, creating fixtures, or testing edge cases." |
| "Explain code" | "Explain what a function or module does in plain English. Use when onboarding, code review, or writing documentation." |

Tips:
- Include the **output artifact** ("summary", "tests", "explanation", "changelog entry")
- Include the **trigger situation** ("when writing a PR", "when onboarding")
- Add **synonyms and related keywords** a user might say

## Output Format

Produces the following files:
- `.resources/prompts/{name}.md` — prompt definition
- `routing/copilot/prompts/{name}.prompt.md` — Copilot slash command routing file
- `routing/claude/.claude/commands/{name}.md` — Claude command routing
- `routing/cursor/.cursor/rules/{name}.mdc` — Cursor rule routing
- `routing/windsurf/.windsurf/rules/{name}.md` — Windsurf rule routing
- New entry in `manifest.yml`

## Naming Conventions

- File names and `id` values MUST be kebab-case (all lowercase, hyphens instead of spaces)
- No spaces, underscores, or uppercase letters in `id` or filename
- Example: `summarize-pr`, `generate-changelog`, `write-commit-message`

## Constraints

- MUST NOT overwrite existing files — if `.resources/prompts/{name}.md` already exists, stop and ask the user
- Validation MUST pass before declaring the prompt creation complete
- All four platform routing steps (Claude, Copilot, Cursor, Windsurf) MUST be addressed
- The `id` field in frontmatter MUST match the filename (stem without `.md`)
