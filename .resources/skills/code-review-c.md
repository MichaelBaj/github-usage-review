---
id: "code-review-c"
version: "1.0.0"
tags: [review, c, systems, security]
applies-to: "**/*.{c,h}"
---

# Code Review — C

## Purpose

High-signal review for changed C files. Focus: memory safety, correctness, security, cleanup
reliability, concurrency, missing validation.

## Scope

- **Selectors:** `*.c`, `*.h`
- **In scope:** manual memory management, buffer math, pointer ownership, signal handlers, thread/shared-state paths, resource cleanup, and low-level API boundaries
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only C-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or include-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Trace ownership across success, error, and early-return paths; free or close exactly once.
- Compare allocation size, element count, loop bounds, and copy length as one coupled contract.
- Check signed/unsigned conversions, overflow, truncation, and sentinel handling before pointer math or allocation.
- Treat format strings, varargs, and null pointers as hostile runtime inputs.
- Review signal handlers for async-signal-safe behavior only.
- Inspect shared-state and lock ordering paths for races, deadlocks, and cleanup under contention.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Memory safety | Copies, indexing, pointer arithmetic, lifetimes after `free`, null handling | read/write can escape object bounds, dereference invalid memory, or use freed storage |
| Integer overflow / underflow | size math, narrowing casts, loop counters, signed/unsigned comparisons | arithmetic can wrap into undersized allocations, infinite loops, or bad bounds checks |
| Format string misuse | `printf`-family, logging helpers, error reporting, externally influenced format strings | attacker-controlled format string or mismatched varargs can read/write memory or crash |
| Buffer-size coupling | `malloc`/`calloc` size, `sizeof` target, `memcpy`/`snprintf` length, struct layout assumptions | allocation size and later usage disagree, enabling overflow or truncation |
| Resource leaks | `FILE*`, sockets, heap memory, mutexes, temporary buffers on failure paths | changed path can leak scarce resources or skip mandatory cleanup |
| Signal safety | handlers calling libc, allocation, logging, locking, or non-atomic state mutation | handler performs non-async-signal-safe work or corrupts shared state |
| Concurrency | lock ordering, unlocked shared state, condition signaling, shutdown sequencing | race or deadlock can occur under normal scheduling or error handling |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Buffer math, parsing, serialization, or copy-length changes | Tests cover boundary sizes, invalid lengths, and zero-length inputs | repo-native build/test target; `ctest --output-on-failure`; sanitizer-enabled run where repo supports it |
| Allocation, ownership, or cleanup changes | Failure-path proof shows no leak, double-free, or null-deref regression | repo-native test target; targeted regression for error paths; AddressSanitizer/LeakSanitizer run if available |
| Signal, threading, or lock-order changes | Evidence from stress or concurrency-focused tests | repo-native concurrency test target; ThreadSanitizer-enabled run or repeated stress test if repo supports it |

## Deep guide (load on demand)

### Memory safety and buffer-size coupling

- Strong reviews treat allocation size, element count, bounds checks, and later use as one invariant.
- Watch for `sizeof(pointer)` vs `sizeof(*pointer)`, off-by-one terminator space, stale aliases after `realloc`, and frees on multiple exits.
- Good fixes add explicit size checks before multiplication and keep ownership obvious at every return path.
- Tests should hit max length, empty input, allocation failure, and malformed-length paths.

### Integer math and format strings

- Wrapping size math often turns into undersized buffers or negative values promoted to huge unsigned lengths.
- Mixed signed/unsigned comparisons can hide underflow or bypass bounds checks.
- Format strings must stay constant unless the caller contract proves them trusted; `%n` exposure is merge-blocking.
- Tests should prove large counts, negative sentinels, and hostile format-like input fail safely.

### Cleanup, signals, and concurrency

- Error handling must release memory, file descriptors, locks, and partial state consistently.
- Signal handlers should set `sig_atomic_t` flags or write to pre-opened fds only; no malloc, printf, or mutex use.
- For threaded code, inspect lock ordering, shared mutable state, shutdown flags, and cleanup while another thread is still using data.
- Tests should exercise interrupted I/O, cancellation/shutdown, and repeated concurrent access.

## Examples

### Buffer-size coupling in allocation
**Issue**
```c
char *copy_name(const char *src, size_t count) {
    char *buf = malloc(count);
    memcpy(buf, src, count + 1);
    return buf;
}
```

**Fix**
```c
char *copy_name(const char *src, size_t count) {
    if (count == SIZE_MAX) return NULL;

    size_t bytes = count + 1;
    char *buf = malloc(bytes);
    if (buf == NULL) return NULL;

    memcpy(buf, src, count);
    buf[count] = '\0';
    return buf;
}
```

**Why it matters:** allocation and write length must match. Boundary tests should prove empty and max-length inputs do not overflow.

### Format string vulnerability
**Issue**
```c
void log_request(const char *user_input) {
    printf(user_input);
}
```

**Fix**
```c
void log_request(const char *user_input) {
    printf("%s", user_input);
}
```

**Why it matters:** attacker-controlled format strings can read or write process memory. Validation should include hostile `%x` and `%n` payloads.

### Signal-unsafe handler
**Issue**
```c
static void on_signal(int signo) {
    printf("caught %d\n", signo);
    cleanup_global_state();
}
```

**Fix**
```c
static volatile sig_atomic_t stop_requested = 0;

static void on_signal(int signo) {
    (void)signo;
    stop_requested = 1;
}
```

**Why it matters:** non-async-signal-safe handlers can deadlock or corrupt state. Validation should prove shutdown happens from normal control flow after signal delivery.
