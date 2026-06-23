---
id: create-skill
version: 1.0.0
tags: [generator, internal, authoring]
---

# keel-new-skill

## Purpose

Scaffold a new ai-keel skill with content, routing for all agents, and manifest entry. Invoke this agent whenever a new skill needs to be added to the repository.

## Copilot Routing Decision

Copilot supports two distinct primitives — choose based on the `applies-to` answer:

| `applies-to` answer | Copilot artifact | Discovery mechanism |
|---|---|---|
| Empty / "all files" / no specific files | **Skill** — `routing/copilot/skills/{name}/SKILL.md` | On-demand: agent loads when description matches task; also available as `/{name}` slash command |
| Specific file pattern (e.g. "Python files") | **Instruction** — `routing/copilot/instructions/{name}.instructions.md` | Automatic: loaded whenever matching files are in context |

Use a **Skill** for on-demand workflows invoked by description relevance or slash command. Use an **Instruction** for always-on standards that apply whenever specific file types are edited.

## Natural Language → Glob Pattern Translation

When the user describes files in natural language, translate to glob patterns:

| User says | `applyTo` glob |
|---|---|
| "all files" / "everything" | `**/*` |
| "Python files" | `**/*.py` |
| "TypeScript files" | `**/*.ts` |
| "TypeScript and JavaScript" | `**/*.{ts,tsx,js,jsx,mjs,cjs}` |
| "React components" | `**/*.{tsx,jsx}` |
| "C++ files" | `**/*.{cpp,cxx,cc,h,hpp,hxx}` |
| "Go files" | `**/*.go` |
| "Rust files" | `**/*.rs` |
| "Java files" | `**/*.java` |
| "C# files" | `**/*.cs` |
| "Markdown / docs" | `**/*.md` |
| "YAML / config" | `**/*.{yml,yaml,json,toml}` |
| "test files" | `**/*.{test,spec}.{ts,js,py}`, `tests/**` |
| "files in src/" | `src/**` |
| "shell scripts" | `**/*.{sh,bash,zsh}` |

For patterns not listed above, construct a reasonable glob and confirm with the user.

## Process

### Extract from Conversation

Before asking questions, review the conversation history. If the user has been enforcing a coding pattern, correcting output, or following a specific workflow, generalize that into the skill definition:
- What recurring rule or workflow are they applying?
- Which files or tasks trigger this concern?
- What would "done" look like?

### 1. Gather Requirements

If the above extraction doesn't provide enough clarity, ask for:
- `name` — kebab-case identifier (e.g., `python-typing`), no spaces, lowercase only
- `description` — what the skill does and **when to invoke it** (see [Writing Effective Descriptions](#writing-effective-descriptions) below)
- `applies-to` — described in natural language (e.g. "all Python files", "TypeScript in src/", or empty for on-demand skill); translate using the table above
- `tags` — comma-separated kebab-case tags (e.g., `python, typing, best-practices`)

Ask only what you can't infer from context.

### 2. Create Skill File

Copy `.resources/skills/_TEMPLATE.md` to `.resources/skills/{name}.md`:
- Set frontmatter: `id: {name}`, `version: 1.0.0`, `tags: [{tags}]`, `applies-to: "{applies-to}"`
- Replace `# <Skill Name>` with `# {Title-Cased Name}`
- Fill in the `## Description` section with the provided description
- Leave other sections with placeholder comments for the user to complete

### 3. Create Claude Routing

Create `routing/claude/.claude/skills/{name}/SKILL.md`:

```markdown
---
name: {name}
description: "{description}"
---

@ref[.resources/skills/{name}.md]
```

### 4. Create Copilot Routing

**Choose one based on the Copilot Routing Decision table above:**

#### Case A — No file pattern → Copilot Skill

Create folder `routing/copilot/skills/{name}/` and file `routing/copilot/skills/{name}/SKILL.md`:

```markdown
---
name: {name}
description: '{keyword-rich description — see Writing Effective Descriptions}'
---

@ref[.resources/skills/{name}.md]
```

> The `name` field must match the folder name exactly. The `description` is the **primary discovery surface** — include the trigger phrases a user would say when they need this skill.

#### Case B — Has file pattern → Copilot Instruction

Create `routing/copilot/instructions/{name}.instructions.md`:

```markdown
---
description: "Use when writing or editing {file description}. {what this enforces}."
applyTo: "{glob-pattern}"
---

@ref[.resources/skills/{name}.md]
```

> `applyTo: "**"` (all files) loads on every interaction and burns context. Only use it for truly universal rules. Prefer specific globs.

### 5. Create Cursor Routing

Create `routing/cursor/.cursor/rules/{name}.mdc`:

```yaml
---
description: "{description}"
globs: ["{glob-pattern}"]
---
@ref[.resources/skills/{name}.md]
```

If the skill has no file scope (universally applicable), omit `globs` to make it Agent Requested.

### 6. Create Windsurf Routing

Create `routing/windsurf/.windsurf/rules/{name}.md`:

```yaml
---
trigger: glob
description: "{description}"
globs: ["{glob-pattern}"]
---
@ref[.resources/skills/{name}.md]
```

If no file scope, use `trigger: model_decision` and omit `globs`.

### 7. Add Manifest Entry

Append the following resource entry to `manifest.yml`:

```yaml
- path: skills/{name}.md
  type: skill
  description: "{description}"
  applies-to: "{applies-to}"
  tags: [{tags}]
```

### 8. Validate

Run the following validation scripts and confirm they pass:
- `uv run scripts/validate_refs.py` — checks all `@ref` targets resolve
- `uv run scripts/validate_manifest.py` — checks manifest conforms to schema

### 9. Iterate

After creating the files:
1. Show the user the generated `description` field and ask if the trigger phrases feel right
2. Identify the weakest part of the skill content and ask a targeted clarifying question
3. Once finalized, summarize what was created and suggest related skills to create next

## Writing Effective Descriptions

The `description` field is the **primary discovery surface** — the agent reads it to decide whether to load this skill. A weak description means the skill is never found.

**Pattern to use:** `"Use when {specific task/trigger}. {keywords the user would say}."`

| ❌ Weak | ✅ Strong |
|---|---|
| "Python coding tips" | "Use when writing Python code. Enforces type hints, docstrings, and PEP 8 naming for Python files." |
| "C++ guidelines" | "Use when writing C++ classes, headers, or templates. Enforces RAII, const-correctness, and include guard conventions." |
| "A helpful skill" | "Use when reviewing a PR or refactoring. Step-by-step checklist for code review, naming conventions, and test coverage." |

Tips:
- Include the **verb** the user would say ("writing", "refactoring", "reviewing", "migrating")
- Include **technology names** as keywords (language, framework, file type)
- Mention **what is enforced** (style, patterns, anti-patterns)
- Keep it under 200 characters for the manifest `description`; the SKILL.md `description` can be up to 1024 characters

## Import Mode

To import an existing skill file into ai-keel structure:

1. **Accept input** — Ask the user for the path to the existing markdown file
2. **Analyze structure** — Detect existing sections, frontmatter presence, and naming
3. **Normalize frontmatter** — Add or correct `id`, `version`, `tags`, and `applies-to` fields per the template contract in `.resources/skills/_TEMPLATE.md`
4. **Restructure sections** — Map existing content to template sections (Description, Core Rules, Examples, References); move misplaced content to the appropriate section
5. **Rename file** — If the filename doesn't follow kebab-case convention, rename to `{normalized-name}.md`
6. **Move to canonical location** — Copy/move the file to `.resources/skills/{name}.md`
7. **Create routing** — Follow the same routing creation steps as for a new skill (steps 3–8 of Process above)
8. **Add manifest entry** — Same as step 9 of Process above
9. **Validate** — Run `python scripts/validate_refs.py` and `python scripts/validate_manifest.py`
10. **Report changes** — List all files created, moved, or modified

## Naming Conventions

- File names and `id` values MUST be kebab-case (all lowercase, hyphens instead of spaces)
- No spaces, underscores, or uppercase letters in `id` or filename
- Skill folder name (for Copilot skill case) MUST match the `name` field exactly
- Example: `python-typing`, `error-handling`, `api-design`

## Guardrails

- MUST NOT overwrite existing files — if `.resources/skills/{name}.md` already exists, stop and ask the user
- Validation MUST pass before declaring the skill creation complete
- All four platform routing steps (Claude, Copilot, Cursor, Windsurf) MUST be addressed
- The `id` field in frontmatter MUST match the filename (stem without `.md`)
- For Copilot skills: the folder name under `routing/copilot/skills/` MUST match the `name` field in `SKILL.md`
