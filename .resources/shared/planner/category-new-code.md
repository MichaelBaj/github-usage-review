# New Code Plans — Category Rules

Selective-load reference for `ai-keel.planner` agent. Load when detected category is **New Code**.

---

1. **Clean code principles** — First phase file includes language clean code principles (Python: PEP 8, type hints, docstrings; TypeScript: strict mode, no `any`; Bash: shellcheck compliance, `set -euo pipefail`).

2. **Task breakdown for sub-agents** — Break each phase into discrete tasks executable independently. Each task must specify: input, output, dependencies, acceptance criteria. Insert inline `> 🔖 CHECKPOINT` after each logical group. Commit at marker, not a separate end section.

3. **Dependency and sequence diagrams** — In `00-overview.md`:
   - Phase dependency graph (Mermaid `graph TD`) — always
   - Sequence diagrams for multi-component interactions — when applicable
   - Module/class relationship diagrams — when applicable
   - Embed as inline ` ```mermaid ``` ` blocks
   - Use `renderMermaidDiagram` during planning

4. **Testing plan** — Each phase includes:
   - Unit test plan with specific test cases per module/function
   - Integration test plan if components interact with others
   - Manual testing instructions for anything not automatable
   - Test data requirements and how to obtain them

5. **Risk focus:**
   - External dep availability and version pinning (tshark, Python libs)
   - MCP tool contract stability (JSON schema, error format)
   - Build/toolchain compatibility across environments
