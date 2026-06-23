---
id: "code-review-javascript"
version: "1.0.0"
tags: [review, javascript, code-review]
applies-to: "**/*.{js,mjs,cjs,jsx}"
---

# Code Review — JavaScript

## Purpose

High-signal review for JavaScript diffs. Review changed scope only. Focus: correctness,
security, reliability, compatibility, missing validation.

## Scope

- **Selectors:** `*.js`, `*.mjs`, `*.cjs`, `*.jsx`
- **In scope:** browser and Node runtime behavior, async control flow, DOM updates, module boundaries, object mutation, and event lifecycle management
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only JavaScript-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Verify every Promise chain and `async` path handles rejection, cancellation, and ordering explicitly.
- Check coercive equality, truthiness, numeric conversion, and date parsing for control-flow or data-loss bugs.
- Inspect object merge and deep-set helpers for prototype pollution through untrusted keys.
- Confirm listeners, timers, observers, caches, and retained closures are removed or bounded with lifecycle.
- Flag unsafe DOM sinks such as `innerHTML`, `insertAdjacentHTML`, or URL-building from untrusted data.
- Keep callback, Promise, and `async`/`await` boundaries consistent so one failure model owns each flow.
- Review ESM/CJS import changes for duplicate singleton state, default-vs-named mismatch, and side-effect imports.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Async failure handling | Missing `.catch()`, ignored returned Promise, `try/catch` that does not await, race-prone state updates | Rejections go unhandled, retries double-run work, or UI/server state commits after failed async work |
| Type coercion traps | `==`, `||` defaults, string-number mixing, `Date` parsing, JSON-to-bool assumptions | Branches or calculations behave differently for valid runtime inputs |
| Prototype pollution | Recursive merge helpers, query-string parsers, JSON patch application, object path setters | Untrusted keys can mutate `Object.prototype` or privileged config objects |
| Memory leaks | Event listeners, intervals, subscriptions, DOM references in closures, growing maps | Objects stay reachable across route changes, requests, or hot paths |
| XSS and unsafe DOM writes | `innerHTML`, template literals in markup, untrusted URLs, `srcdoc`, unsafe sanitization assumptions | User-controlled content can execute script or inject active markup |
| Module boundary drift | Mixed ESM/CJS imports, top-level side effects, duplicated singletons, cyclic init | Runtime loads wrong export, initializes twice, or depends on import order |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Async flow or state sequencing change | Tests prove rejection path, retry path, and ordering-sensitive updates behave deterministically | repo test command; `npm test -- <target>` |
| DOM rendering or template change | Evidence covers safe escaping, expected markup, and no script execution from untrusted content | repo UI/integration test first; otherwise targeted component or browser test |
| Object merge or config parsing change | Proof that attacker-controlled keys cannot pollute prototypes and config remains scoped | repo security test first; otherwise targeted regression around merge helper |
| Import or packaging change | Build/test output proves selected runtime resolves expected exports once | repo build/test command; fallback build command for changed package |

## Deep guide (load on demand)

### Async rejection and sequencing
- JavaScript failures disappear when Promise-returning functions are called without `await` or returned chain handling.
- Strong fixes choose one async style per flow, await work before catching, and serialize state updates when ordering matters.
- Tests should force rejection, retry, and out-of-order completion cases.

### Type coercion and runtime values
- Browser inputs, query params, and JSON payloads arrive as strings or nullable values even when code reads like typed data.
- Strong fixes normalize values once at boundary and use strict comparisons plus explicit parsing.
- Tests should include `"0"`, empty string, `null`, `undefined`, and invalid date/number values.

### Prototype pollution
- Generic merge utilities become security boundaries when they accept untrusted object keys.
- Strong fixes reject `__proto__`, `prototype`, and `constructor`, or merge into null-prototype objects with allowlisted keys.
- Tests should prove polluted keys do not appear on fresh objects after merge.

### Memory lifecycle
- Closures can retain DOM nodes, request contexts, and large response objects long after feature path ends.
- Strong fixes unregister listeners, clear timers, and scope caches to explicit lifecycle owners.
- Tests or profiling should exercise mount/unmount or repeated request loops.

### XSS and module boundaries
- Untrusted HTML, URL fragments, and side-effect imports often mix correctness bugs with security bugs.
- Strong fixes prefer text nodes over HTML sinks and keep module initialization explicit and idempotent.
- Tests should prove import order does not change behavior and unsafe content renders inertly.

## Examples

### Unhandled rejection in `try/catch`
**Issue**
```javascript
async function saveProfile(api, profile) {
  try {
    api.update(profile);
    toast('Saved');
  } catch (error) {
    toast(error.message);
  }
}
```

**Fix**
```javascript
async function saveProfile(api, profile) {
  try {
    await api.update(profile);
    toast('Saved');
  } catch (error) {
    toast(error.message);
  }
}
```

**Why it matters:** `try/catch` only observes awaited failures. Validation should prove rejected updates do not show success toast.

### Prototype-polluting merge helper
**Issue**
```javascript
function applyPatch(target, patch) {
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === 'object') {
      target[key] ??= {};
      applyPatch(target[key], value);
    } else {
      target[key] = value;
    }
  }
}
```

**Fix**
```javascript
const BLOCKED_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

function applyPatch(target, patch) {
  for (const [key, value] of Object.entries(patch)) {
    if (BLOCKED_KEYS.has(key)) continue;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      target[key] ??= Object.create(null);
      applyPatch(target[key], value);
    } else {
      target[key] = value;
    }
  }
}
```

**Why it matters:** Untrusted object paths can mutate global object behavior. Validation should prove `({}).polluted` stays `undefined` after patch application.

### XSS through HTML sink and leaked listener
**Issue**
```javascript
function mountBanner(root, message) {
  root.innerHTML = `<p>${message}</p>`;
  window.addEventListener('resize', () => console.log(root.offsetWidth));
}
```

**Fix**
```javascript
function mountBanner(root, message) {
  const text = document.createElement('p');
  text.textContent = message;
  root.replaceChildren(text);

  const onResize = () => console.log(root.offsetWidth);
  window.addEventListener('resize', onResize);
  return () => window.removeEventListener('resize', onResize);
}
```

**Why it matters:** Untrusted markup can execute, and anonymous listeners cannot be cleaned up. Validation should prove hostile text renders inertly and repeated mount/unmount does not grow listener count.
