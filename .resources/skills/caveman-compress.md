---
id: "caveman-compress"
version: "1.0.0"
tags: [communication, token-efficiency, compression, memory]
applies-to: "**/*.md"
---

# Caveman Compress

## Description

Compress prose-heavy memory files, notes, preferences, TODOs, or CLAUDE-style context files into caveman format to cut token cost without losing technical substance. Use when: token bloat; memory file too long; context budget pressure; compress notes before reuse; shrink session memory; preserve code blocks, inline code, headings, and URLs; overwrite original after validation. Trigger: /caveman:compress <filepath> or "compress memory file".

## Core Rules

### No-Compress Targets

**NEVER compress caveman skill files themselves** (`caveman.md`, `caveman-commit.md`, `caveman-compress.md`). These files ARE the compression standard — compressing them is circular and counter-productive. They are already written in their target format.

### Process

1. **Guard: skip non-compressible files.**
   - Skip if extension is `.py`, `.js`, `.ts`, `.json`, `.yaml`, `.yml`, `.toml`, `.env`, `.lock`, `.sh`, `.css`, `.html`, `.xml`, `.sql`
   - Skip if filename matches credential/secret patterns (`.pem`, `.key`, `credentials.*`, `secrets.*`, etc.)
   - Skip if file is a caveman skill (`caveman*.md` in a skills directory)
   - Proceed only for `.md`, `.txt`, `.markdown`, `.rst`, or extensionless files

2. **Read file in full and record pre-compression metrics.**
   Run `wc -lwc <filepath>` to get line, word, char counts. Store in session memory.

3. **Compress section by section.**
   Work heading-by-heading. For each section:
   - Identify code blocks: copy EXACTLY, no changes
   - Apply compression rules to all prose between blocks
   - Never merge content across heading boundary
   - Files ≥300 lines: compress in ~100-line chunks, track output, then join

4. **Write compressed result.**
   Write full compressed content to original path (overwriting).

5. **Validate against pre-compression metrics.**
   Run `wc -lwc <filepath>` for post-compression metrics. Compare:
   - All headings present and unmodified
   - No code blocks changed
   - All URLs intact
   - `post_lines < pre_lines` and `post_words < pre_words`
   - `post_words >= pre_words * 0.40` (guards against data loss)

6. **Report to user.**
   State: original path (compressed in-place), pre/post line+word counts, reduction %.

### Compression Rules

**Remove:**
- Articles: a, an, the
- Filler: just, really, basically, actually, simply, essentially, generally
- Pleasantries: "sure", "certainly", "of course", "happy to", "I'd recommend"
- Hedging: "it might be worth", "you could consider", "it would be good to"
- Redundant phrasing: "in order to" → "to", "make sure to" → "ensure", "the reason is because" → "because"
- Connective fluff: "however", "furthermore", "additionally", "in addition"

**Preserve EXACTLY (never modify):**
- Code blocks (fenced ``` and indented)
- Inline code (`backtick content`)
- URLs and links (full URLs, markdown links)
- File paths (`/src/components/...`, `./config.yaml`)
- Commands (`npm install`, `git commit`, `docker build`)
- Technical terms (library names, API names, protocols, algorithms)
- Proper nouns (project names, people, companies)
- Dates, version numbers, numeric values
- Environment variables (`$HOME`, `NODE_ENV`)

**Preserve Structure:**
- All markdown headings (keep exact heading text, compress body below)
- Bullet point hierarchy (keep nesting level)
- Numbered lists (keep numbering)
- Tables (compress cell text, keep structure)
- Frontmatter/YAML headers in markdown files

**Compress:**
- Short synonyms: "big" not "extensive", "fix" not "implement a solution for", "use" not "utilize"
- Fragments OK: "Run tests before commit" not "You should always run tests before committing"
- Drop "you should", "make sure to", "remember to" — state action directly
- Merge redundant bullets saying same thing
- Keep one example where multiple show same pattern

**CRITICAL:** Anything inside ``` ... ``` must be copied EXACTLY. Inline code (`...`) must be preserved EXACTLY.

## Examples

### ✅ Correct

Original:
> You should always make sure to run the test suite before pushing any changes to the main branch. This is important because it helps catch bugs early and prevents broken builds from being deployed to production.

Compressed:
> Run tests before push to main. Catch bugs early, prevent broken prod deploys.

Original:
> The application uses a microservices architecture with the following components. The API gateway handles all incoming requests and routes them to the appropriate service. The authentication service is responsible for managing user sessions and JWT tokens.

Compressed:
> Microservices architecture. API gateway route all requests to services. Auth service manage user sessions + JWT tokens.

### ❌ Avoid

- Modifying code blocks
- Changing inline code content
- Removing headings
- Compressing below 40% of original word count (data loss)
- Compressing caveman skill files themselves

## Boundaries

- Compress only `.md`, `.txt`, extensionless
- NEVER modify: `.py`, `.js`, `.ts`, `.json`, `.yaml`, `.yml`, `.toml`, `.env`, `.lock`, `.css`, `.html`, `.xml`, `.sql`, `.sh`
- NEVER compress: caveman skill files (`caveman*.md` in skills directories)
- Mixed content: compress prose sections only
- Unsure if code or prose: leave unchanged

## References

- [caveman](.resources/skills/caveman.md) — parent communication mode
