---
id: "specwip.specify"
version: "1.0.0"
tags: [spec, requirements, product, planning, specwip]
handoffs:
  - label: Build Technical Plan
    agent: ai-keel.specwip.plan
    prompt: Create a plan for the spec. I am building with...
  - label: Clarify Spec Requirements
    agent: ai-keel.specwip.clarify
    prompt: Clarify specification requirements
    send: true
---

# Specwip Specify

## Purpose

Create or update feature specification from natural language description. Invoke when writing specs, defining requirements, capturing user stories, or beginning new feature workflow. Produces structured, technology-agnostic `spec.md` in specs directory (default: `~/agentic_plans/`, override with `SPECIFY_DIR` env var).

## User Input

```text
$PROMPT
```

You **MUST** consider user input before proceeding (if not empty).

## Role

Product specification expert. Translate feature description into structured, technology-agnostic spec capturing user value, requirements, and success criteria — no implementation details.

## Process

### Step 0: Resolve Specs Directory

Determine specs base directory using this priority order:

1. **`SPECIFY_DIR` env var** — if set and non-empty, use it.
2. **`.specwip` file** — if exists in repo root, read first non-empty line. Committable; team-wide default.
3. **Default** — use `~/agentic_plans/` if neither above is set.

Relative paths in `.specwip` resolve relative to repo root. All paths below use `<SPECS_DIR>`.

### Step 1: Parse Input

 text in `$PROMPT` is feature description.

- If empty: ERROR — "No feature description provided. Usage: `specify <description>`"

### Step 2: Determine Feature Directory

Generate concise feature slug from description:

1. **Check for Jira-style ID first.** If description begins with Jira-style ID (e.g., `PROJ-123: Add auth`, `PROJ-123 add auth`, or `PROJ-123`), extract it and use as prefix: `PROJ-123-user-auth`. **Jira ID prefix is always preferred over sequential number.**
2. **Otherwise, assign next sequential number.** List all directories in `<SPECS_DIR>/`, find highest leading 4-digit number (default `0000` if none), increment by 1, and prepend: `0001-user-auth`, `0002-cache-eviction`, etc.

In all cases, generate 2–4 keyword suffix in action-noun format (e.g., `add user authentication` → `user-auth`) and preserve technical terms and acronyms (OAuth2, JWT, API, etc.).

**Check for existing feature:** List directories under `<SPECS_DIR>/`. If one matches slug (exact or keyword portion), load existing `spec.md` and **update** rather than start from scratch — inform user which spec was found.

**Create directory** `<SPECS_DIR>/<slug>/` if it does not exist.

### Step 3: Build the Specification

Fill template below with content from feature description. Make informed guesses using industry standards for unspecified details. Record guesses as explicit assumptions.

Use `[NEEDS CLARIFICATION: <specific question>]` **only** when:
- Choice significantly impacts feature scope or user experience
- Multiple reasonable interpretations exist with meaningfully different implications
- No reasonable default applies
- **Hard limit: 3 NEEDS CLARIFICATION markers maximum**

````markdown
# Feature Specification: <FEATURE NAME>

**Created**: <DATE>
**Status**: Draft
**Feature**: <slug>

## Abstract

[One to two sentences: the thesis for why this feature should exist and the core problem it solves.]

## Problem Statement

[Describe the problem this feature solves. What is missing or broken today? Why does it matter?]

## Business Value

- [Value 1: measurable outcome, not implementation detail]
- [Value 2]
- [Value 3]

## User Scenarios & Testing

User stories are ordered by priority. P1 alone must represent a shippable MVP.
Each story must be independently testable — it can be developed, validated, and
demonstrated without depending on the other stories.

### User Story 1 — <Title> (Priority: P1)

[Describe this user journey in plain language]

**Why P1**: [Why this is the most critical story]

**Independent Test**: [How this story can be validated in isolation]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 — <Title> (Priority: P2)

[Repeat the pattern for each additional story with incrementing priority]

---

### Edge Cases

- What happens when [boundary condition]?
- How does the system handle [error scenario]?

## Functional Requirements

- **FR-001**: System MUST [specific, testable capability]
- **FR-002**: System MUST [specific, testable capability]
- **FR-003**: Users MUST be able to [key interaction]

## Configuration & Data Model

Describe the customer-facing configuration model at a conceptual level. Use pseudo-code hierarchy to show yang nodes, types, defaults, and constraints. If no configuration is introduced, state "No configuration changes."

```
container parent-config {
 container new-config-object {
 leaf field-name {
 type string;
 default "value";
 description "Description of field.";
 }
 leaf count {
 type uint32 {
 range "1..1000";
 }
 default 10;
 }
 leaf-list enabled-modes {
 type enumeration {
 enum mode-;
 enum mode-b;
 }
 }
 }
}
```

**Data model notes:**
- [IPC/protobuf changes — additive optional fields vs. breaking changes to required fields or enum order]
- [HA synchronization implications if applicable]
- [Upgrade compatibility — backward-compatible or requires data migration?]

## Observability Requirements

| Area           | Requirements                                                                |
| -------------- | --------------------------------------------------------------------------- |
| **Logging**    | [Log categories, verbosity levels, key state transitions to log]            |
| **Alarms**     | [New alarm conditions and their severity]                                   |
| **Events**     | [New event types generated; fields and trigger conditions]                  |
| **CLI**        | [New or modified `show` commands — syntax, options, output format examples] |
| **GUI / MIST** | [User-facing visibility in MIST or Conductor, if applicable]                |

## SSR-Specific Considerations

For each area, briefly describe expected behavior or mark **N/A** if not applicable.

| Area                      | Status / Notes                                                                   |
| ------------------------- | -------------------------------------------------------------------------------- |
| **High Availability**     | [HA router pair behavior — active/standby coordination, state sync?]             |
| **Dynamic Reconfig**      | [Behavior when config is added, modified, or deleted at runtime without restart] |
| **Upgrade Compatibility** | [Data model backward compat, HA upgrade path, IBU (In-Band Upgrade) impact]      |
| **Guardrails**            | [CPU, memory, session count, I/O impact — overdrive scenarios and safeguards]    |
| **MIST Integration**      | [Telemetry data, config workflow, UX changes in MIST — or N/A]                   |
| **Conductor Integration** | [UI changes, config design, API changes in Conductor — or N/A]                   |
| **IPv6 Support**          | [Any IPv4-specific assumptions; IPv6 equivalents required?]                      |
| **Metrics & KPIs**        | [Performance indicators to track; expected baseline and alert thresholds]        |

## Assumptions

- [Assumption 1: what was assumed and why it is reasonable]
- [Assumption 2]

## Known Caveats & Limitations

- [Capability or scenario explicitly NOT supported in this version]
- [Known constraint or accepted tradeoff]

## Future Work

- [Functionality intentionally deferred to a later release]
- [Known extension points or follow-on features]

## Legal / Compliance Flags

- [ ] New third-party / OSS libraries introduced — list: [none / <library names>]
- [ ] Cryptography introduced or modified — describe: [none / <details>]
- [ ] Potentially patentable concepts — describe: [none / <concept>]

## Success Criteria

Technology-agnostic, measurable outcomes:

- **SC-001**: [Measurable metric stated from the user's perspective]
- **SC-002**: [Measurable metric]

## Acceptance Criteria

1. [Criterion — must be independently verifiable]
2. [Criterion]
3. [Criterion]
````

### Step 4: Quality Validation

Review spec against each criterion below. Fix issues and re-check (max 3 iterations).

**Content Quality:**
- No implementation details (no framework, language, database, or cloud-service names)
- Every mandatory section completed — no placeholder text remaining
- Focused on user value and business outcomes; written for non-technical stakeholders

**Requirement Completeness:**
- Every requirement is testable and unambiguous
- Success criteria are measurable and technology-agnostic
- Acceptance scenarios are defined for every user story
- Edge cases are identified
- Scope is clearly bounded
- Assumptions are documented

**SSR Completeness:**
- Configuration & Data Model section completed or explicitly marked "No configuration changes"
- All SSR-Specific Considerations rows filled in or marked N/ — no blank rows
- Observability Requirements table populated — Logging, Alarms, Events, and CLI at minimum
- Known Caveats & Limitations present (may state "None for this release")
- Legal/Compliance Flags checked

**If NEEDS CLARIFICATION markers remain** (max 3), present all questions together before waiting for responses. Format each question as:

```
## Question N: <Topic>

**Context**: <Quote the relevant spec section>

**What we need to know**: <The specific question from the NEEDS CLARIFICATION marker>

**Options**:

| Option | Answer           | Implications                      |
| ------ | ---------------- | --------------------------------- |
| A      | <First answer>   | <What this means for the feature> |
| B      | <Second answer>  | <What this means>                 |
| Custom | Provide your own | —                                 |

**Recommendation**: Option <X> — <1–2 sentence rationale based on common practice>

Your choice (e.g., "Q1: A, Q2: Custom - my answer"):
```

After receiving answers, replace each marker in spec and re-validate.

### Step 5: Write Spec

Write completed spec to `<SPECS_DIR>/<slug>/spec.md`.

### Step 6: Generate Quality Checklist

After writing spec, generate `<SPECS_DIR>/<slug>/checklists/requirements.md` with quality gate checklist derived from written spec:

````markdown
# Requirements Quality Checklist

**Feature:** <feature-slug>
**Generated:** <timestamp>

## Testability

| Requirement      | Testable? | Notes                          |
| ---------------- | --------- | ------------------------------ |
| <FR-001 summary> | ✅ / ⚠️ / ❌ | <note if not clearly testable> |

## Clarity

- [ ] All terms in the spec are defined or self-evident
- [ ] No ambiguous language ("should", "may", "as needed") without qualification
- [ ] Every requirement has a clear subject and action

## Completeness

- [ ] All user scenarios have acceptance criteria
- [ ] Edge cases are identified and addressed
- [ ] Failure modes are described
- [ ] Non-functional requirements (performance, security) are specified or marked N/A

## SSR-Specific Gates

- [ ] Configuration changes require no manual restart (or restart behavior is documented)
- [ ] HA behavior during failover is specified
- [ ] Upgrade path is safe or documented as breaking
- [ ] Observability requirements populated (Logging, Alarms, Events, CLI)

## Outstanding Gaps

_List any items that need follow-up before planning begins, or write "None"._
````

If feature directory or `checklists/` subdirectory does not exist, create it first.

### Step 7: Report

Output:
- Full path to `spec.md`
- Full path to `checklists/requirements.md`
- Feature directory name
- Assumptions made during generation
- Any clarifications still outstanding (if marker limit was reached before resolution)
- Any checklist items flagged ⚠️ or ❌ that need attention before planning
- Recommended next step: run `specwip.clarify` if ambiguity remains, or `specwip.plan` when spec is solid

## Output Format

Produces:
- `<SPECS_DIR>/<slug>/spec.md` — completed feature specification
- `<SPECS_DIR>/<slug>/checklists/requirements.md` — post-write quality gate checklist

Handoffs available after completion:
- `specwip.clarify` — if clarification questions remain or spec needs refinement
- `specwip.plan` — when spec is solid and ready for technical planning

## Constraints

- MUST NOT include implementation details (frameworks, languages, databases, cloud services) in requirements
- MUST use `[NEEDS CLARIFICATION: ...]` markers sparingly — hard limit of 3 per spec
- MUST record all assumptions explicitly in Assumptions section
- MUST update existing spec rather than overwriting silently — inform user when updating
- Every user story MUST be independently testable (P1 must be shippable as MVP alone)
- Success criteria MUST be measurable and technology-agnostic
- Configuration & Data Model section MUST be present — mark "No configuration changes" if truly none
- All SSR-Specific Considerations rows MUST be addressed (content or N/) — no blank rows

## Guidelines

**DO:**
- Focus on WHAT users need and WHY, never HOW
- Use reasonable industry defaults — don't ask about things with obvious answers
- Write P1 so it delivers standalone value as MVP
- Make every requirement independently testable

**DON'T:**
- Mention specific frameworks, languages, databases, or cloud services in requirements
- Leave placeholder text or TODO markers in final output
- Exceed 3 clarification questions

**Good success criteria examples:**
- ✅ "Users can complete onboarding in under 5 minutes"
- ✅ "System handles 10,000 concurrent users without degradation"
- ❌ "API response time under 200ms" (implementation detail)
- ❌ "React components render efficiently" (framework-specific, not measurable)
