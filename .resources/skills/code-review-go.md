---
id: "code-review-go"
version: "1.0.0"
tags: [review, go, concurrency, systems]
applies-to: "**/*.go"
---

# Code Review — Go

## Purpose

High-signal review for changed Go files. Focus: error handling, concurrency safety, cancellation,
API correctness, missing validation.

## Scope

- **Selectors:** `*.go`
- **In scope:** errors, goroutines, channels, contexts, defer/recover patterns, interface boundaries, shared-state concurrency, and public package behavior
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only Go-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Every returned `error` must be handled, wrapped with context, or intentionally ignored with proof that loss is safe.
- Goroutines need bounded lifetime, cancellation path, and receiver/sender shutdown coordination.
- Channel send, receive, and close ownership must be explicit; inspect for deadlock on slow or gone consumers.
- Propagate caller `context.Context`; do not replace it with `context.Background()` in request-scoped work.
- Check `defer` timing in loops, named-return mutation, and panic recovery for hidden behavior changes.
- Distinguish interface nil from typed-nil concrete values, and expect `go test -race` evidence when shared state changes.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Ignored or weakly handled errors | dropped returns, `_ = err`, missing wraps, partial writes, cleanup errors | failure can be silently lost, retried incorrectly, or reported without enough context |
| Goroutine leaks | blocked sends/receives, unbounded workers, missing shutdown, background tasks after request exit | goroutine can live forever or keep resources after caller is done |
| Channel deadlocks | send/receive ordering, buffered capacity assumptions, close ownership, fan-in/out shutdown | normal scheduling can block forever or panic on close/send race |
| Race conditions | shared maps, slices, cached state, loop variable capture, unsynchronized mutation | behavior depends on scheduling and lacks synchronization or immutability |
| Context misuse | dropped deadlines, ignored cancellation, `Background()` replacement, child work outliving caller | request-scoped work continues after cancellation or timeout |
| Defer gotchas | `defer` inside loops, `recover` swallowing panics, named-return mutation, deferred close ordering | cleanup happens too late, panic is masked, or returned value changes unexpectedly |
| Interface nil confusion | typed nil stored in interface, custom error types, nil receiver methods | nil checks lie and callers take wrong control-flow path |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Behavior, API, or error-path changes | Tests assert returned errors, wrapping, and partial-failure behavior | `go test ./...`; targeted `go test ./path/to/pkg -run <name>` |
| Goroutine, channel, or shared-state changes | Evidence includes cancellation/shutdown tests and race coverage | `go test -race ./...`; targeted package test for changed concurrency path |
| Timeout, retries, or request-scoped work changes | Tests prove deadline propagation and cancellation stop downstream work | `go test ./...`; focused package test exercising canceled context or slow consumer path |

## Deep guide (load on demand)

### Error handling and interface boundaries

- Ignored errors are often real behavior changes, especially around I/O, marshaling, flush, and close operations.
- Prefer `%w` wrapping when callers need to preserve chain semantics; avoid losing root cause behind generic strings.
- Typed-nil values inside interfaces or `error` can make `err != nil` lie; inspect constructor and return sites together.
- Tests should assert exact error behavior for malformed input, partial failure, and wrapped downstream errors.

### Goroutines, channels, and context propagation

- Every spawned goroutine needs an exit condition tied to consumer lifetime, channel closure, or context cancellation.
- Inspect blocking sends after caller exits, workers without bounded queues, and goroutines launched in library helpers without ownership rules.
- Context deadlines and values should flow through outbound calls, loops, and retries unless code is explicitly detached by design.
- Tests should cancel context mid-operation, stop receivers early, and run with `-race` on changed shared state.

### Defer and panic behavior

- `defer` in loops delays cleanup until function exit, which can exhaust descriptors or locks.
- Deferred closures over named returns can mutate results in non-obvious ways.
- `recover` is only safe when code converts panic into explicit error semantics and preserves observability.
- Tests should cover panic paths, repeated loop iterations, and cleanup ordering under early return.

## Examples

### Blocked send leaks goroutine
**Issue**
```go
func sendResult(ctx context.Context, ch chan<- Result, work func() Result) {
    go func() {
        ch <- work()
    }()
}
```

**Fix**
```go
func sendResult(ctx context.Context, ch chan<- Result, work func() Result) {
    go func() {
        result := work()
        select {
        case ch <- result:
        case <-ctx.Done():
        }
    }()
}
```

**Why it matters:** blocked sends can leak goroutines after cancellation. Validation should cancel caller before consumer receives.

### Lost error context
**Issue**
```go
func loadConfig(path string) error {
    _, err := os.ReadFile(path)
    if err != nil {
        return err
    }
    return nil
}
```

**Fix**
```go
func loadConfig(path string) error {
    _, err := os.ReadFile(path)
    if err != nil {
        return fmt.Errorf("read config %q: %w", path, err)
    }
    return nil
}
```

**Why it matters:** unwrapped errors hide failing operation and break caller diagnostics. Validation should assert wrapped error chain and message context.

### Typed nil in interface
**Issue**
```go
type customError struct{}

func (*customError) Error() string { return "boom" }

func maybeError(fail bool) error {
    if !fail {
        var err *customError
        return err
    }
    return &customError{}
}
```

**Fix**
```go
type customError struct{}

func (*customError) Error() string { return "boom" }

func maybeError(fail bool) error {
    if !fail {
        return nil
    }
    return &customError{}
}
```

**Why it matters:** typed nil stored in `error` compares non-nil and sends callers down wrong path. Validation should assert both fail and non-fail branches.
