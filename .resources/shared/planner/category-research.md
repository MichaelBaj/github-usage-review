# Non-Code / Research Plans — Category Rules

Selective-load reference for `ai-keel.planner` agent. Load when detected category is **Research**.

---

1. **Structured research workflow** — Define Question → Gather Evidence → Analyze → Synthesize → Recommend. Each phase with specific deliverables.

2. **Explain with analogies** — Use relatable analogies to make complex topics accessible. Example: *"Think of this like building a LEGO model — you need the instruction booklet (the spec), the sorted brick piles (the data sources), and a flat surface to work on (the test environment)."*

3. **Concrete examples** — Reference actual files, configs, or logs from this repo; show before/after; include sample outputs.

4. **Visual aids** — In `00-overview.md`:
   - Concept maps (Mermaid `graph` or `mindmap`)
   - Decision trees for architecture choices
   - Flow diagrams for proposed processes
   - Embed inline; use `renderMermaidDiagram` during planning

5. **Adapted decomposition:**
   - **Level 1 — Questions**: What decisions need to be made?
   - **Level 2 — Evidence areas**: What info needed per question?
   - **Level 3 — Sources**: Docs, experiments, benchmarks, expert input
   - **Level 4 — Tasks**: Read doc X, benchmark approach Y, prototype option Z

6. **Decision framework** — In synthesis phase:
   - Options with pros/cons
   - Evaluation criteria with weights
   - Recommended option with justification
   - "Considered and rejected" alternatives with reasons

7. **Risk focus:**
   - Analysis paralysis — hard deadline for decision
   - Confirmation bias — gather evidence for *all* options
   - Scope creep — define "done" criteria upfront
