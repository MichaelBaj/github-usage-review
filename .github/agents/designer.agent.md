---
name: designer
description: Autonomous detail-design agent. Takes a phase plan file produced by the planning agent and generates a comprehensive design document with API contracts, function signatures, data models, Mermaid sequence/component diagrams, file-by-file change specs, edge cases, error handling, and unit test cases. Design docs live alongside phase files in ~/agentic_plans/ and are named xx-phase-<name>-design.md.
argument-hint: Provide the path to a phase plan file (e.g., ~/agentic_plans/2026-04-30-ai-keel-foundation/02-phase-generators.md) and optionally describe any design constraints or preferences.
tools: [read,edit,search,web,todo,vscode/askQuestions,vscode/memory]
---

@ref[.resources/agents/designer.md]
