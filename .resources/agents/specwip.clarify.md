---
id: "specwip.clarify"
version: "1.0.0"
tags: [spec, requirements, clarification, questions, specwip]
handoffs:
  - label: Build Technical Plan
    agent: ai-keel.specwip.plan
    prompt: Create a plan for the spec. I am building with...
---

# Specwip Clarify

## Purpose

Loop targeted clarification questions until shared understanding; encode answers back into `spec.md`. Invoke after `specwip.specify`, before `specwip.plan` when ambiguity remains. SSR: also probes HA, dynamic reconfig, MIST, Conductor, IPv6, upgrade compatibility.

## User Input

```text
$PROMPT
```

You **MUST** consider user input before proceeding (if not empty).

## Role

Requirements analyst. Detect ambiguity and missing decision points in spec, resolve through targeted dialogue, record outcomes in spec — spec is single source of truth before planning.

## Workflow

### Step 0: Resolve Specs Directory

Determine specs base directory using this priority order:

1. **`SPECIFY_DIR` env var** — if set and non-empty, use it.
2. **`.specwip` file** — if exists in repo root, read first non-empty line. Committable; team-wide default.
3. **Default** — use `~/agentic_plans/` if neither above is set.

Relative paths in `.specwip` resolve relative to repo root. All paths below use `<SPECS_DIR>`.

### Step 1: Locate the Feature

Determine active feature directory using this priority order:

1. If `$PROMPT` contains path or feature name, search `<SPECS_DIR>/` for matching directory (exact, then partial match on slug).
2. If `$PROMPT` is empty:
 - List all subdirectories of `<SPECS_DIR>/`.
 - If one: use it automatically, tell user.
 - If multiple: list and ask user to specify.
 - If none exist: ERROR — "No features found. Run `specify` first."

Load `<SPECS_DIR>/<slug>/spec.md`. If file does not exist, ERROR — "spec.md not found. Run `specify` first."

### Step 2: Ambiguity Scan

Structured coverage scan across taxonomy. Assess each: **Clear** / **Partial** / **Missing**. Build internal priority queue (don't output raw map).

| Category                       | What to look for                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| **Functional Scope**           | Core user goals, explicit out-of-scope declarations, actor/role distinctions             |
| **Domain & Data**              | Key entities, identity/uniqueness rules, lifecycle/state transitions, volume assumptions |
| **User Interaction**           | Critical journeys and sequences, error/empty/loading states                              |
| **Non-Functional Quality**     | Performance targets, reliability/availability, security & privacy posture, compliance    |
| **Integrations**               | External services and failure modes, data formats, protocol assumptions                  |
| **Edge Cases & Failures**      | Negative scenarios, rate limiting, conflict resolution                                   |
| **Constraints & Tradeoffs**    | Explicit technical constraints, rejected alternatives                                    |
| **Completion Signals**         | Testability of acceptance criteria, measurable definition-of-done indicators             |
| **Placeholders**               | TODO markers, vague adjectives ("robust", "intuitive") lacking quantification            |
| **SSR: High Availability**     | HA router pair behavior — does active/standby need coordination? Is state synced?        |
| **SSR: Dynamic Reconfig**      | Runtime config add/modify/delete behavior — service continuity, state cleanup            |
| **SSR: Upgrade Path**          | Data model compatibility across versions, HA upgrade order, IBU impact                   |
| **SSR: Guardrails**            | Memory/CPU/session impact — can feature be overdriven? Safeguards needed?                |
| **SSR: MIST Integration**      | Telemetry, config, or UX changes required in MIST?                                       |
| **SSR: Conductor Integration** | UI, config, or API changes required in Conductor?                                        |
| **SSR: IPv6**                  | Any IPv4-only assumptions? IPv6 equivalents required?                                    |
| **SSR: Observability**         | Alarms, events, logging, CLI commands — all identified and specified?                    |

Add candidate question for each Partial or Missing category **unless**:
- Clarification would not materially change implementation or validation strategy
- information is better deferred to planning (note internally, flag in summary)

### Step 3: Generate Question Queue

From candidate pool, rank by:
- (Impact × Uncertainty) — prefer questions reducing downstream rework
- Coverage balance — avoid two low-impact questions when high-impact gap (e.g., security posture) unresolved
- Exclude already answered, trivial stylistic, or plan-level execution details

Each question answerable via:
- multiple-choice (2–5 mutually exclusive options), **or**
- short-phrase (constrain: "Answer in ≤5 words")

No arbitrary question limit — loop until confident of shared understanding of all high-impact requirements.

Do **not** reveal upcoming questions.

### Step 4: Sequential Questioning Loop

> **⚠️ VIBE-KANBAN / HEADLESS MODE RULE**
> When running inside automated harness (vibe-kanban, ACP, or any context where
> you cannot detect interactive terminal), you **MUST**:
> 1. Output first question using format below.
> 2. **STOP IMMEDIATELY** after question — no answers, no placeholders, no commentary.
> 3. Do **NOT** call any tools after outputting question.
> 4. Do **NOT** write "Waiting for your response" or any filler text.
> 5. user will reply in chat; their reply triggers next turn.
>
> Violating this rule by self-answering defeats purpose of clarification.

Present **one question at time**.

**For multiple-choice questions**, format as:

```
**Question N of [estimated total]: <Topic>**

<One-sentence context explaining why this matters>

**Recommended**: Option <X> — <1–2 sentence rationale>

| Option | Description                           |
| ------ | ------------------------------------- |
| A      | <Option A>                            |
| B      | <Option B>                            |
| C      | <Option C>                            |
| Short  | Provide a different answer (≤5 words) |

Reply with the option letter, "yes"/"recommended" to accept the recommendation,
or a short custom answer.
```

**For short-answer questions**, format as:

```
**Question N of [estimated total]: <Topic>**

<One-sentence context>

**Suggested**: <Your proposed answer> — <brief reasoning>

Format: Short answer (≤5 words). Reply "yes"/"suggested" to accept, or provide your own.
```

**After each answer:**
- If user replies "yes", "recommended", or "suggested", use stated recommendation.
- Validate response maps to option or fits ≤5-word constraint; disambiguate if unclear (not a new question).
- Record answer in working memory.
- Write into `spec.md` **immediately** (see Step 5).
- Proceed to next question.

Stop when:
- Fully confident of mutual, shared understanding of all high-impact requirements
- User signals completion ("done", "good", "proceed", "no more")

If no meaningful ambiguities: respond "No critical ambiguities detected — spec is ready for planning." Suggest `specwip.plan`.

### Step 5: Incremental Spec Updates (after each accepted answer)

Apply clarification to spec file immediately after each answer is accepted — do not batch writes.

**Session header (first answer only):** If no `## Clarifications` section, create it after last non-appendix section. Add `### Session <YYYY-MM-DD>`.

**Log entry:** Append `- Q: <question> → A: <accepted answer>` under session heading.

**Propagate change to relevant section:**

| Answer type               | Where to update in spec                                                                 |
| ------------------------- | --------------------------------------------------------------------------------------- |
| Functional ambiguity      | Add/update bullet in **Functional Requirements**                                        |
| Actor or role distinction | Update user story titles or add actor note in **User Scenarios**                        |
| Data shape / state        | Add entity note or state transition in **Assumptions** or new **Data Notes** subsection |
| Non-functional constraint | Add measurable criterion to **Success Criteria**                                        |
| Edge case or failure mode | Add bullet to **Edge Cases**                                                            |
| Terminology conflict      | Normalize term across all sections; note `(formerly "X")` once if needed                |

**Rules for updating:**
- Replace ambiguous text, don't duplicate — no contradictions in final spec
- Keep insertions minimal and testable (no narrative drift)
- Preserve heading hierarchy; only introduce `## Clarifications` and `### Session <date>`
- Save `spec.md` after **every** write

### Step 6: Final Validation

After loop ends, verify:

- [ ] `## Clarifications` session contains exactly one bullet per accepted answer (no duplicates)
- [ ] Updated sections contain no lingering vague placeholders answers were meant to resolve
- [ ] No contradictory earlier statements remain
- [ ] Markdown structure is valid
- [ ] Canonical terms are used consistently across all updated sections

### Step 7: Report

Output:
- Number of questions asked and answered
- Path to updated `spec.md`
- Sections touched (by name)
- Coverage summary table:

| Category         | Status                                    |
| ---------------- | ----------------------------------------- |
| Functional Scope | Resolved / Deferred / Clear / Outstanding |
| …                | …                                         |

- If Outstanding or Deferred remain, note whether to re-run `specwip.clarify` or proceed to `specwip.plan`
- Recommended next step

## Output Format

Produces:
- Updated `<SPECS_DIR>/<slug>/spec.md` — with clarifications encoded directly into relevant sections
- `## Clarifications` section appended to `spec.md` logging each Q→ pair per session

## Constraints

- MUST loop until confident of mutual, shared understanding of all high-impact requirements.
- MUST write answers into `spec.md` immediately after each accepted answer — no batching
- MUST NOT reveal upcoming questions in advance
- MUST NOT create new spec if `spec.md` is missing — instruct user to run `specwip.specify` first
- MUST respect early termination signals ("stop", "done", "proceed")
- MUST avoid speculative technology-stack questions unless absence blocks functional clarity
- If questions are deferred or postponed by user, flag them explicitly as **Deferred**
