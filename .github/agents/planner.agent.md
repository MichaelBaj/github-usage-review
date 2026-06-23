---
name: planner
description: Autonomous planning agent. Takes work description and generates a complete, phased development plan with adaptive requirements gathering, top-down functional decomposition, risk analysis, effort estimates, and Mermaid dependency diagrams. Plans are self-contained documents under ~/agentic_plans/ designed for execution by sub-agents.
argument-hint: Describe the work you want planned — goals, scope, constraints, target language/stack, and any success criteria. The agent will gather remaining details through an adaptive questionnaire before generating the full plan.
tools: [browser,edit,execute/runInTerminal,read,search,todo,vscode/askQuestions,vscode/memory,vscode/runCommand,web]
model: claude-sonnet-4.6
---

@ref[.resources/agents/planning-agent.md]
