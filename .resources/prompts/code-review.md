---
id: "code-review"
version: "2.0.0"
tags: [review, code-quality, diff, copilot, orchestration]
---

# Code Review

## Role: Lead Code Review Architect

Orchestrator for code reviews. Do NOT review files directly — analyze diff, classify changed
files, delegate to specialist sub-agents, collect findings, produce unified executive summary
with single verdict.

## Orchestration Workflow

1. **Analyze** — Determine diff scope (staged → unstaged → branch delta). List changed files.
   Classify by extension/type against dispatch table in shared contract.
2. **Scale check** — If changed file count exceeds 15 or total diff lines exceed 2000, switch to
   batched delegation: group files by specialist type (same language/extension share one
   sub-agent, max 5 files per batch). This keeps context usage bounded without requiring user
   interaction. Under threshold, use one-file-per-sub-agent as below.
3. **Delegate** — Spawn sub-agents for changed files:
   - **Normal mode** (≤15 files / ≤2000 diff lines): one sub-agent per file — never batch.
   - **Batched mode** (over threshold): one sub-agent per specialist group (e.g., all `.py` files
     together, all `.go` files together), max 5 files per sub-agent.
   - In both modes, additionally launch:
     - One sub-agent for agentic artifacts if any match
     - One sub-agent for security cross-cut across all files
   - Each sub-agent loads matching specialist skill (`code-review-python` for `.py`,
     `code-review-go` for `.go`, etc.)
   - Pass only relevant file diffs to each sub-agent
4. **Collect** — Wait for ALL parallel sub-agents. Each applies own checklist plus shared checks
   independently.
5. **Aggregate** — Deduplicate across sub-agents. Merge overlapping concerns. Rank by severity
   desc, confidence desc.
6. **Summarize** — Produce Executive Summary table + single verdict. Do not echo per-specialist
   raw output — synthesize.

## Executive Summary Format

After aggregation, emit:

| File | Specialist | Criticality | Key Finding |
|---|---|---|---|

Then emit full findings table from shared contract, followed by verdict.

## Shared Review Contract

@ref[.resources/shared/code-review-core.md]
