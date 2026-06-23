---
id: "code-review-robot"
version: "1.0.0"
tags: [review, automation, robot-framework, testing, qa]
applies-to: "*.robot"
---

# Code Review — Robot Framework

## Purpose

High-signal review for Robot Framework suites, resources, and keyword-driven UI/API automation.
Review changed scope only. Focus: flaky waits, brittle selectors, state leakage, teardown
failures, debugging gaps that hide regressions.

## Scope

- **Selectors:** `*.robot`
- **In scope:** Test-case structure, keyword design, resource layering, variable scope, setup/teardown behavior, selectors, logging, and parallel-safe automation patterns
- **Out of scope:** Shared guidance owned by `.resources/skills/code-review.md`; library implementation code in other languages should use its matching language skill

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete flaky or masked-failure modes.

## Compact checklist

- Check that tests stay keyword-driven: reusable business-level keywords in resources, assertions close to behavior, and no giant copy-pasted test bodies.
- Replace fixed sleeps with condition-based waits that bound time and fail with actionable diagnostics.
- Review resource-file boundaries, imports, and keyword ownership so shared setup stays reusable without hidden cross-suite coupling.
- Verify variable scope stays minimal; avoid `Set Global Variable` or suite-level state that bleeds between tests unless isolation is explicit.
- Require teardown and cleanup to run reliably after partial setup, failure, or timeout, with evidence capture when debugging matters.
- Prefer stable selectors (`id`, `data-*`, accessible hooks, API contract fields) over brittle XPath or index-based locators.
- Check parallel execution safety: unique test data, isolated temp files/accounts, and logs/screenshots keyed per test.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Flaky waits | `Sleep`, polling loops, weak `Wait Until` usage, missing timeouts | Test depends on timing luck, can hang too long, or fails without telling what condition never arrived |
| Selector brittleness | XPath chains, positional locators, text-only selectors, unstable CSS | Minor DOM/content change breaks tests or selector can hit wrong element silently |
| Variable-scope leakage | `Set Suite Variable`, `Set Global Variable`, mutable lists/dicts shared across tests | One test can affect another, parallel runs collide, or teardown depends on hidden global state |
| Resource and keyword sprawl | Huge suites, duplicated keywords, cyclic resource imports, low-level Selenium steps in tests | Behavior changes require scattered edits or failures become hard to reason about |
| Teardown and evidence gaps | Setup/teardown keywords, cleanup ordering, screenshot/log capture on failure | Failed or interrupted runs leave state behind or lose debugging evidence needed to reproduce issue |
| Parallel isolation | Shared accounts, files, ports, env vars, output dirs, external fixtures | Parallel workers race, overwrite artifacts, or make suite nondeterministic |
| Logging noise or silence | `Log`/`Log To Console` overuse, missing contextual logs, secret-bearing logs | Failures become unreadable, logs leak sensitive data, or root cause cannot be reconstructed |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Test or keyword logic change | Proof that affected suites still pass and failures stay actionable | Repo-native Robot test target first; fallback: targeted `robot <suite_or_folder>` run for changed area |
| Wait, retry, or selector change | Evidence that automation resists timing variance and DOM/API drift | Focused UI/API regression first; fallback: repeat changed test multiple times and inspect failure diagnostics |
| Resource-file or variable-scope change | Proof that suites remain isolated and imports/variables resolve in intended scope | Suite-level test target first; fallback: `robot --dryrun <suite>` plus targeted real run exercising changed keywords |
| Setup/teardown or cleanup change | Evidence that cleanup runs after failure and debugging artifacts survive | Existing failure-path test first; fallback: inject controlled failure and verify teardown plus logs/screenshots |
| Parallel-execution change | Proof that concurrent workers do not share mutable state or artifacts unsafely | Repo-native parallel target first; fallback: `pabot` or repeated concurrent suite run if project uses parallel Robot tooling |

## Deep guide (load on demand)

### Keyword structure and resource organization

- Tests should read as behavior, not as long driver scripts. Low-level UI or API choreography belongs in reusable keywords, usually in resource files near shared fixtures.
- Watch for duplicated keyword bodies across suites; drift creates inconsistent assertions and uneven teardown.
- Strong fixes move shared behavior into resource files, keep test cases short, and keep keyword names outcome-oriented.
- Validation should prove moved keywords still expose same arguments and failure messages.

### Wait strategy and selector stability

- `Sleep` is weak evidence that system is ready. It slows happy path and still flakes when environment is slower than guessed delay.
- Prefer `Wait Until Element Is Visible`, `Wait Until Keyword Succeeds`, API polling with bounded timeout, or domain-specific readiness keywords.
- Selector review should prefer durable hooks: IDs, `data-testid`, stable contract fields, or accessibility labels. Deep XPath and positional CSS often encode layout, not intent.
- Validation should run changed tests repeatedly or under slower conditions to prove timing and locator stability.

### Variable scope and teardown reliability

- Scope creep is common in Robot because suite/global variables look convenient. Review whether state can stay local to keyword or test instead.
- Global or suite variables become dangerous when tests run in different order or in parallel.
- Teardowns must tolerate partial setup. Cleanup keywords should not assume every resource was created successfully.
- Strong fixes keep data local, return values explicitly between keywords, and use teardown keywords that check for resource existence before cleanup.

### Parallel safety and logging

- Parallel Robot runs need unique accounts, files, ports, and output locations. Shared fixtures should be immutable or explicitly synchronized.
- Debuggability matters: too much logging hides signal, but too little leaves flaky failures unexplained.
- Strong fixes tag logs with test context, capture screenshots or response bodies only on failure, and avoid logging secrets or giant blobs every step.
- Validation should include at least one parallel or repeated run and inspection of generated logs for actionable failure context.

## Examples

### Fixed sleep instead of condition-based wait

**Issue**
```robot
*** Test Cases ***
User Can Save Profile
    Click Button    css:button.save
    Sleep    5s
    Element Text Should Be    css:.toast    Saved
```

**Fix**
```robot
*** Test Cases ***
User Can Save Profile
    Click Button    css:button.save
    Wait Until Element Is Visible    css:.toast    timeout=10s
    Element Text Should Be    css:.toast    Saved
```

**Why it matters:** Fixed sleeps create flaky tests and waste runtime when system is fast. Validation should rerun changed test multiple times under variable load.

### Global variable causing cross-test leakage

**Issue**
```robot
*** Keywords ***
Remember Created User
    [Arguments]    ${username}
    Set Global Variable    ${CREATED_USER}    ${username}
```

**Fix**
```robot
*** Keywords ***
Remember Created User
    [Arguments]    ${username}
    Set Test Variable    ${created_user}    ${username}
```

**Why it matters:** Global state lets unrelated tests depend on execution order and breaks parallel isolation. Validation should run affected suite in different orders or workers.

### Brittle XPath and teardown with weak evidence

**Issue**
```robot
*** Test Cases ***
Admin Can Delete User
    Click Element    xpath=//table/tbody/tr[3]/td[7]/button
    Click Button    Delete

*** Settings ***
Teardown    Close Browser
```

**Fix**
```robot
*** Test Cases ***
Admin Can Delete User
    Click Element    css:[data-testid="delete-user"]
    Click Button    Delete

*** Settings ***
Teardown    Run Keywords    Capture Page Screenshot    AND    Close Browser
```

**Why it matters:** Positional XPath breaks on harmless layout changes, and bare teardown loses failure context. Validation should prove selector survives DOM rearrangement and screenshot appears on failure.
