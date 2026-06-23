---
id: "code-review-python"
version: "1.0.0"
tags: [review, python, code-review]
applies-to: "**/*.{py,pyi}"
---

# Code Review — Python

## Purpose

High-signal review for Python diffs. Review changed scope only. Focus: correctness, security,
reliability, compatibility, missing validation.

## Scope

- **Selectors:** `*.py`, `*.pyi`
- **In scope:** runtime type contracts, exception and resource handling, import-time behavior, async boundaries, subprocess and filesystem access, data-layer call sites
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only Python-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Verify type hints still match runtime values, optionality, and container element types returned on real paths.
- Flag bare `except`, swallowed exceptions, and fallback returns that mask unrelated failures.
- Check mutable defaults, module globals, caches, and import-time work for shared-state or side-effect bugs.
- Confirm files, sockets, locks, DB sessions, and subprocess pipes close on success and failure paths.
- Inspect `async`/`await` changes for missing awaits, blocking sync work in event-loop paths, and cancellation handling.
- Review SQL, shell, and filesystem inputs for injection or path traversal through Python-specific APIs.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| Type-contract drift | Annotated return types, `TypedDict` usage, optional fields, `Protocol` or stub assumptions | Callers can receive runtime shapes or `None` values that violate annotated contracts |
| Exception masking | `except:`, `except Exception`, logging without re-raise, broad retry wrappers | Real failures become silent fallback values, partial writes, or false success |
| Shared mutable state | Default args, module caches, singleton clients, import-time initialization | Requests or tests bleed state across calls or imports trigger irreversible work |
| Resource lifetime | `open()`, DB sessions, network clients, temp files, locks, context managers | Resources leak, flush/close never happens, or cleanup skips on error paths |
| Async boundary misuse | Missing `await`, `create_task()` without supervision, blocking I/O in coroutine, ignored cancellation | Event loop stalls, tasks leak, or failures surface outside intended error handling |
| Python-specific injection | f-string SQL, `subprocess.*(..., shell=True)`, `Path` joins with user input | Untrusted input can execute commands, alter queries, or escape intended directories |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Type or model contract change | Tests prove returned runtime values still satisfy hinted shape on success and failure paths | `uv run pytest`; targeted `uv run pytest path/to/test_file.py -k <case>` |
| Exception or cleanup path change | Tests exercise error path, cleanup, and rollback behavior instead of success-only assertions | `uv run pytest`; focused regression test for raised exception and cleanup side effects |
| Async workflow change | Evidence covers cancellation, timeout, and awaited failure handling | repo async test target first; otherwise targeted `uv run pytest path/to/test_file.py -k async` |
| DB, shell, or path handling change | Proof that untrusted input fails closed and normal input still works | repo integration/security test first; otherwise targeted regression around query or command wrapper |

## Deep guide (load on demand)

### Type-contract drift
- Python annotations document expected shapes, but runtime objects can still drift through unchecked deserialization, partial dicts, or widened return branches.
- Strong fixes validate external data before casting it into trusted domain objects and keep `Optional` handling explicit.
- Tests should cover malformed, partial, and unexpected payloads, not only happy-path fixtures.

### Exception handling and resource cleanup
- Broad exception handlers often hide broken imports, programming errors, and partial writes.
- Strong fixes catch only expected exception types, preserve traceback context, and use `with` blocks or `try/finally` for cleanup.
- Tests should prove unrelated exceptions still fail loudly while expected recoverable errors take intended fallback path.

### Global state and import side effects
- Module-level network calls, env mutation, logger reconfiguration, and singleton caches make import order matter.
- Strong fixes move expensive or stateful work behind functions, dependency injection, or explicit startup hooks.
- Tests should import module multiple ways or across test cases to prove state does not leak between runs.

### Async and await pitfalls
- Python async code breaks when coroutine results are not awaited, sync I/O blocks event loop, or background tasks outlive request lifecycle.
- Strong fixes keep async stacks consistent, bound task lifetime, and handle cancellation explicitly where cleanup matters.
- Tests should force timeout, cancellation, and exception propagation paths.

### Injection and path safety
- Parameterized SQL, argv lists for subprocess calls, and path normalization are not optional wrappers; they are correctness boundaries.
- Strong fixes separate data from commands, reject traversal segments, and scope filesystem access to approved roots.
- Tests should cover attacker-controlled values like quote characters, `..`, and shell metacharacters.

## Examples

### Mutable default and swallowed exception
**Issue**
```python
def load_user(user_id: str, cache: dict[str, dict] = {}):
    try:
        return cache[user_id]
    except Exception:
        return None
```

**Fix**
```python
def load_user(user_id: str, cache: dict[str, dict] | None = None):
    cache = {} if cache is None else cache
    try:
        return cache[user_id]
    except KeyError:
        return None
```

**Why it matters:** Shared mutable state leaks across calls and broad exception handling hides unrelated bugs. Validation should prove cache misses return `None` without masking other failures.

### Import side effect and leaked file handle
**Issue**
```python
CONFIG = json.load(open("settings.json"))
```

**Fix**
```python
def load_config(path: str = "settings.json") -> dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
```

**Why it matters:** Importing module now depends on local filesystem state and leaves cleanup to GC. Validation should prove imports stay side-effect free and config loading closes file handle on error.

### Unsafe query and shell construction
**Issue**
```python
def export_user(conn, user_id: str, output_dir: str) -> None:
    conn.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
    subprocess.run(f"tar -czf {output_dir}/users.tgz users", shell=True, check=True)
```

**Fix**
```python
def export_user(conn, user_id: str, output_dir: Path) -> None:
    conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    archive_path = (output_dir / "users.tgz").resolve()
    archive_path.relative_to(output_dir.resolve())
    subprocess.run(["tar", "-czf", str(archive_path), "users"], check=True)
```

**Why it matters:** Python string interpolation crosses directly into SQL and shell parsers. Validation should prove attacker-controlled IDs and traversal attempts do not change executed query or archive path.
