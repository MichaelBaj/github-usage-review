---
id: create-agent
version: 1.0.0
tags: [generator, internal, authoring]
---

# keel-new-agent

## Purpose

Scaffold a new ai-keel agent definition with process steps, routing for all agents, and manifest entry. Invoke this agent whenever a new agent process document needs to be added to the repository.

## Extract from Conversation

Before asking questions, review the conversation history. If the user has been following a multi-step workflow or methodology (e.g., debugging approach, review checklist, implementation pattern), generalize it into an agent definition. Extract:
- The step-by-step process being followed
- When the user would invoke this agent vs. just asking in chat
- What outputs the agent produces

## Process

### 1. Gather Requirements

Ask only what you can't infer from context:
- `name` — kebab-case identifier (e.g., `code-reviewer`), no spaces, lowercase only
- `purpose` — what this agent does and when to invoke it (1–2 sentences; see [Writing Effective Descriptions](#writing-effective-descriptions))
- `trigger` — how a user invokes it (e.g., `@code-reviewer`, "when reviewing a PR", slash command name)
- `output-format` — what the agent produces (files, messages, edits, etc.)
- `tags` — comma-separated kebab-case tags (e.g., `review, quality, automation`)

### 2. Create Agent File

Copy `.resources/agents/_TEMPLATE.md` to `.resources/agents/{name}.md`:
- Set frontmatter: `id: {name}`, `version: 1.0.0`, `tags: [{tags}]`
- Replace `# <Agent Name>` with `# {Title-Cased Name}`
- Fill in the `## Purpose` section with the provided purpose
- Fill in the `## Output Format` section with the provided output format description
- Leave the `## Process` and `## Constraints` sections with placeholder comments for the user to complete

### 3. Create Claude Routing

Create `routing/claude/.claude/skills/{name}/SKILL.md`:

```markdown
---
name: {name}
description: "{description}"
---

@ref[.resources/agents/{name}.md]
```

Also create `routing/claude/.claude/commands/{name}.md`:

```markdown
@ref[.resources/agents/{name}.md]
```

### 4. Create Copilot Routing

Create `routing/copilot/agents/{name}.agent.md`:

```markdown
---
name: {name}
description: '{keyword-rich description — see Writing Effective Descriptions}'
---

@ref[.resources/agents/{name}.md]
```

> The `description` field is the **primary discovery surface**. Copilot reads it to decide when to load the agent. Include the verbs and keywords a user would say when they need this agent.

### 5. Create Cursor Routing

Create `routing/cursor/.cursor/rules/{name}.mdc`:

```yaml
---
description: "{description}"
---
@ref[.resources/agents/{name}.md]
```

### 6. Create Windsurf Routing

Create `routing/windsurf/.windsurf/rules/{name}.md`:

```yaml
---
trigger: model_decision
description: "{description}"
---
@ref[.resources/agents/{name}.md]
```

### 7. Add Manifest Entry

Append the following resource entry to `manifest.yml`:

```yaml
- path: agents/{name}.md
  type: agent
  description: "{purpose (first sentence, ≤200 chars)}"
  tags: [{tags}]
```

### 8. Validate

Run the following validation scripts and confirm they pass:
- `uv run scripts/validate_refs.py` — checks all `@ref` targets resolve
- `uv run scripts/validate_manifest.py` — checks manifest conforms to schema

### 9. Iterate

After creating the files:
1. Show the user the generated `description` field and ask if the trigger phrases feel right
2. Identify the most ambiguous step in the `## Process` section and ask a clarifying question
3. Once finalized, summarize what was created and suggest the next agent or skill to create

## Writing Effective Descriptions

The `description` field in `routing/copilot/agents/{name}.agent.md` controls when Copilot loads this agent. A vague description means the agent is never invoked.

**Pattern:** `"{Verb} when {specific situation}. {keywords user would say}."`

| ❌ Weak | ✅ Strong |
|---|---|
| "Code review helper" | "Review code for correctness, naming, and test coverage. Use when reviewing a PR, inspecting a diff, or auditing a function." |
| "Release tool" | "Generate a changelog entry and release notes. Use when cutting a release, bumping a version, or summarizing commits." |
| "Test agent" | "Scaffold unit tests for a function or module. Use when adding tests, improving coverage, or generating test fixtures." |

Tips:
- Include the **action verb** ("review", "generate", "scaffold", "migrate", "refactor")
- Include **trigger phrases** the user would actually type
- Mention **what the agent produces** (file, message, edit)

## Output Format

Produces the following files:
- `.resources/agents/{name}.md` — agent process definition
- `routing/copilot/agents/{name}.agent.md` — Copilot agent routing file
- `routing/claude/.claude/skills/{name}/SKILL.md` — Claude skill routing
- `routing/cursor/.cursor/rules/{name}.mdc` — Cursor rule routing
- `routing/windsurf/.windsurf/rules/{name}.md` — Windsurf rule routing
- New entry in `manifest.yml`

## Naming Conventions

- File names and `id` values MUST be kebab-case (all lowercase, hyphens instead of spaces)
- No spaces, underscores, or uppercase letters in `id` or filename
- Example: `code-reviewer`, `release-noter`, `test-scaffolder`

## Constraints

- MUST NOT overwrite existing files — if `.resources/agents/{name}.md` already exists, stop and ask the user
- Validation MUST pass before declaring the agent creation complete
- All four platform routing steps (Claude, Copilot, Cursor, Windsurf) MUST be addressed
- The `id` field in frontmatter MUST match the filename (stem without `.md`)
- Generator agents (`ai-keel.create-*`) are internal — do NOT use this process for generator agents; generators are created manually
