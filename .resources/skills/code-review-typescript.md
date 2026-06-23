---
id: "code-review-typescript"
version: "1.0.0"
tags: [review, typescript, code-review]
applies-to: "**/*.{ts,mts,cts,tsx}"
---

# Code Review — TypeScript

## Purpose

High-signal review for TypeScript diffs. Review changed scope only. Focus: correctness,
security, reliability, compatibility, missing validation.

## Scope

- **Selectors:** `*.ts`, `*.mts`, `*.cts`, `*.tsx`
- **In scope:** static types at module boundaries, runtime validation, generic APIs, nullable data flows, union exhaustiveness, and guard functions
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only TypeScript-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Prefer specific types over `any`, and verify narrowing still protects every runtime access path.
- Flag `as Type`, non-null assertions, and double-casts when they replace validation or exhaustiveness.
- Check compile-time types against runtime inputs from JSON, forms, storage, and network boundaries.
- Review generics for missing constraints, variance surprises, and fallback defaults that accept invalid shapes.
- Confirm null and undefined handling stays explicit under `strictNullChecks`, especially across optional chaining and defaults.
- Inspect discriminated unions and `switch` statements for true exhaustiveness when new variants land.
- Verify custom type guards test actual runtime properties and cannot lie to compiler.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| `any` leakage | Public APIs, deserialization boundaries, helper returns, generic defaults | Unsafe values bypass narrowing and cause unchecked property access or wrong writes |
| Assertion abuse | `as`, `!`, `unknown as T`, JSON casts, DOM casts | Runtime can still hold invalid shape while compiler assumes safety |
| Runtime/schema drift | DTOs, config, env parsing, browser storage, form payloads | Compiled code accepts malformed runtime input and fails later in deeper layers |
| Generic constraint gaps | Unbounded `T`, overly broad defaults, inferred key types, collection helpers | APIs accept unsupported shapes or return misleadingly precise types |
| Nullability mistakes | Optional fields, fallback values, union narrowing, async data states | `null`/`undefined` path reaches property access, serialization, or control flow incorrectly |
| Discriminated union or guard bugs | Missing `never` checks, stale discriminants, weak guard predicates | New variants fall through silently or guards claim unsupported data is safe |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Type boundary or DTO change | Proof that runtime validation still rejects malformed payloads before typed use | repo test command; `tsc --noEmit -p <tsconfig>` |
| Generic helper or utility type change | Tests show representative callers still infer safe types and runtime behavior matches | repo test command; targeted tests for changed helper |
| Union or state-machine change | Evidence covers every variant, including unreachable/default branch protection | repo test command; fallback `tsc --noEmit -p <tsconfig>` |
| Nullable data-flow change | Tests prove empty/loading/error states do not hit unsafe property access | repo component/unit test first; targeted regression for null path |

## Deep guide (load on demand)

### `any` and narrowing discipline
- `any` is contagious: one widened helper can erase safety across many callers.
- Strong fixes keep unknown data as `unknown`, then narrow it with validation or well-scoped guards.
- Tests should include malformed payloads that exercise every narrowing branch.

### Assertion abuse versus validation
- `as Type` changes compiler opinion, not runtime data.
- Strong fixes validate external input, use parser/schema helpers where repo already has them, and reserve assertions for proven invariants.
- Tests should prove bad payloads fail at boundary instead of later property access.

### Generics and constraints
- Generic helpers often promise more than implementation can guarantee, especially around keys, partial updates, and collection transforms.
- Strong fixes constrain `T`, preserve readonly or optional semantics intentionally, and avoid return types that overclaim exactness.
- Tests should cover edge callers, widened inference, and invalid generic instantiations.

### Nullability and discriminated unions
- Optional chaining can hide state gaps when code still assumes presence later in same flow.
- Strong fixes branch explicitly on discriminants, use `never` checks for exhaustiveness, and keep nullable values out of success types.
- Tests should cover loading, empty, error, and newly added union members.

### Type guard correctness
- Type guards are executable code and can lie if they only check one shallow property.
- Strong fixes test all properties required for safe downstream use and avoid broad truthiness checks.
- Tests should prove guards reject partial objects and mixed-shape payloads.

## Examples

### Assertion instead of runtime validation
**Issue**
```ts
type User = { profile: { name: string } };

function getUserName(payload: unknown): string {
  const user = payload as User;
  return user.profile.name.toUpperCase();
}
```

**Fix**
```ts
type User = { profile: { name: string } };

function hasUser(value: unknown): value is User {
  return typeof value === 'object'
    && value !== null
    && typeof (value as { profile?: { name?: unknown } }).profile?.name === 'string';
}

function getUserName(payload: unknown): string {
  if (!hasUser(payload)) throw new Error('Invalid payload');
  return payload.profile.name.toUpperCase();
}
```

**Why it matters:** Compile-time assertion does not protect runtime input. Validation should prove malformed payloads fail closed.

### Missing exhaustiveness in discriminated union
**Issue**
```ts
type Job =
  | { kind: 'queued' }
  | { kind: 'running'; startedAt: number }
  | { kind: 'failed'; error: string };

function label(job: Job): string {
  switch (job.kind) {
    case 'queued':
      return 'Queued';
    case 'running':
      return `Running since ${job.startedAt}`;
    default:
      return 'Done';
  }
}
```

**Fix**
```ts
type Job =
  | { kind: 'queued' }
  | { kind: 'running'; startedAt: number }
  | { kind: 'failed'; error: string };

function assertNever(value: never): never {
  throw new Error(`Unhandled job state: ${JSON.stringify(value)}`);
}

function label(job: Job): string {
  switch (job.kind) {
    case 'queued':
      return 'Queued';
    case 'running':
      return `Running since ${job.startedAt}`;
    case 'failed':
      return job.error;
    default:
      return assertNever(job);
  }
}
```

**Why it matters:** New or existing variants can disappear into misleading fallback labels. Validation should prove every union member is rendered intentionally.

### Weak generic constraint and nullability bug
**Issue**
```ts
function getValue<T>(record: T, key: string) {
  return record[key as keyof T];
}
```

**Fix**
```ts
function getValue<T extends Record<string, unknown>, K extends keyof T>(record: T, key: K): T[K] {
  return record[key];
}
```

**Why it matters:** Unconstrained generics and asserted keys overpromise safety. Validation should prove invalid keys fail at compile time and callers handle nullable values explicitly.
