# Refactor Plans — Category Rules

Selective-load reference for `ai-keel.planner` agent. Load when detected category is **Refactor**.

---

1. **Current state analysis** — First phase documents:
   - What exists today (file list, key functions, current behavior)
   - Why refactor needed (pain points, tech debt, scaling)
   - **Pros and cons** of refactor vs. not
   - Risk assessment: what could break

2. **Structured execution workflow** — Prepare → Extract → Transform → Validate → Clean up. Each phase with:
   - Explicit entry/exit criteria
   - Rollback instructions
   - Inline checkpoints at entry/exit boundaries

3. **Inter-dependency visualization** — In `00-overview.md`:
   - Current module/file dependencies (before) as Mermaid diagram
   - Target dependencies (after) as Mermaid diagram
   - Highlight what changes
   - Embed as inline blocks; use `renderMermaidDiagram` during planning

4. **Regression prevention** — Each phase includes:
   - Existing test coverage and gaps
   - Regression test suite to run at each checkpoint
   - Before/after behavioral equivalence checks
   - Which existing tests must continue to pass

5. **Risk focus:**
   - Breaking existing consumers (MCP tool signatures, CLI flags, output formats)
   - Merge conflicts with in-flight work
   - Test coverage gaps hiding regressions
