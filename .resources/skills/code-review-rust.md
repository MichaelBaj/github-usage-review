---
id: "code-review-rust"
version: "1.0.0"
tags: [review, rust, ownership, systems]
applies-to: "**/*.rs"
---

# Code Review — Rust

## Purpose

High-signal review for changed Rust files. Focus: ownership correctness, unsafe contracts, async
reliability, panic boundaries, concurrency, missing validation.

## Scope

- **Selectors:** `*.rs`
- **In scope:** ownership and borrowing decisions, lifetime design, `unsafe` blocks, clone behavior, async/cancellation paths, synchronization, and public error contracts
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only Rust-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Respect ownership and borrowing; challenge clones that hide unnecessary copies, stale state, or wrong ownership boundaries.
- Review lifetime annotations and returned references against actual data ownership, not compiler-satisfying workarounds.
- Audit every `unsafe` block for documented invariants, aliasing, initialization, bounds, and thread-safety assumptions.
- Prefer `Result` propagation over `panic!`, `unwrap`, or `expect` in library and recoverable runtime paths.
- Inspect async code for cancellation safety, drop behavior, and locks or borrows held across `.await`.
- Check mutex/lock poisoning, error propagation, and shutdown coordination in concurrent code.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Ownership and borrowing mistakes | moved values, aliasing expectations, interior mutability, returned references | fix relies on clone churn or invalid sharing instead of clear ownership model |
| Lifetime annotation errors | borrowed return values, struct lifetimes, iterator/view APIs, temporary values | references can outlive backing data or API forces unsound lifetime coupling |
| `unsafe` block review | raw pointers, `MaybeUninit`, FFI, `Send`/`Sync` impls, slice construction | safety contract is undocumented, violated, or unverifiable from surrounding code |
| Clone skepticism | `.clone()` added to satisfy borrow checker, repeated Arc/String/Vec cloning, stale snapshots | clone masks ownership bug, adds surprising cost, or breaks shared-state expectations |
| Cancellation safety in async | partial writes, dropped futures, select branches, locks across `.await`, cleanup on cancel | cancellation can lose data, deadlock, or leave invariant half-updated |
| Error handling: `Result` vs panic | `unwrap`, `expect`, `panic!`, conversion boundaries, library APIs | recoverable failure aborts task/process or violates caller contract |
| Mutex poisoning | `lock().unwrap()`, panic inside critical section, poison recovery, state rollback | poisoned lock crashes normal recovery path or exposes inconsistent shared state |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Ownership, borrowing, lifetime, or public API changes | Compile and test evidence proves signatures and call sites still fit intended ownership model | `cargo check`; `cargo test`; targeted `cargo test <module_or_test>` |
| `unsafe`, concurrency, or synchronization changes | Evidence covers invariant-preserving tests and concurrent failure paths | repo-native unsafe/concurrency test target; `cargo test`; focused regression for changed path |
| Async, cancellation, or error-contract changes | Tests prove cancel/drop behavior, retry semantics, and non-panicking failure handling | `cargo test`; targeted async test for changed flow; repo-native integration test target if available |

## Deep guide (load on demand)

### Ownership, borrowing, and clone skepticism

- New clones deserve suspicion when they appear only to appease borrow checker complaints.
- Prefer restructuring scopes, borrowing narrower slices, or moving ownership explicitly instead of duplicating data by default.
- Watch for APIs returning references tied to temporaries, hidden `Rc<RefCell<_>>` complexity, and interior mutability that weakens invariants.
- Tests should cover repeated calls, mutation after borrow-heavy paths, and performance-sensitive hot loops if clones were added.

### Lifetimes and unsafe contracts

- Lifetime annotations should describe true ownership relationships, not force unrelated values to share one lifetime parameter.
- `unsafe` code must state and uphold invariants: initialized bytes, alignment, aliasing, valid length, thread affinity, and drop behavior.
- Review nearby safe wrappers, not only `unsafe` lines themselves; unsound safe APIs are merge-blocking even when block is small.
- Tests should exercise boundary lengths, FFI contract edges, and invalid-input handling around unsafe surfaces.

### Async cancellation and poisoned locks

- Futures can be dropped at any `.await`; review whether partial state updates roll back or leave system consistent.
- Never hold mutex guards, write guards, or blocking resources across `.await` unless primitive is built for it and scope is intentional.
- `lock().unwrap()` after panic turns transient failure into wider outage; consider poison recovery or state reset path.
- Tests should cancel tasks mid-flight, panic inside critical sections, and verify next caller still gets coherent behavior.

## Examples

### Recoverable error should return `Result`
**Issue**
```rust
fn parse_port(value: &str) -> u16 {
    value.parse().expect("invalid port")
}
```

**Fix**
```rust
fn parse_port(value: &str) -> Result<u16, std::num::ParseIntError> {
    value.parse()
}
```

**Why it matters:** panics in normal parsing paths break callers that could handle error cleanly. Validation should cover malformed input without process abort.

### Holding mutex guard across `.await`
**Issue**
```rust
async fn refresh(state: Arc<Mutex<Client>>) {
    let mut client = state.lock().unwrap();
    client.reload().await;
}
```

**Fix**
```rust
async fn refresh(state: Arc<Mutex<Client>>) {
    let request = {
        let client = state.lock().unwrap();
        client.build_reload_request()
    };

    let response = send_reload(request).await;

    let mut client = state.lock().unwrap();
    client.apply_reload(response);
}
```

**Why it matters:** holding blocking mutex across `.await` can deadlock or starve unrelated work. Validation should cancel or interleave concurrent refresh calls.

### Unsafe slice length contract drift
**Issue**
```rust
fn read_words(ptr: *const u16, byte_len: usize) -> &'static [u16] {
    unsafe { std::slice::from_raw_parts(ptr, byte_len) }
}
```

**Fix**
```rust
fn read_words<'a>(owner: &'a [u16], byte_len: usize) -> Option<&'a [u16]> {
    if byte_len % std::mem::size_of::<u16>() != 0 {
        return None;
    }

    let len = byte_len / std::mem::size_of::<u16>();
    owner.get(..len)
}
```

**Why it matters:** raw-part lengths are element counts, not bytes, and returned lifetime must match caller-owned data. Validation should exercise odd lengths and short buffers.
