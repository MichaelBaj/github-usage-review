"""In-memory response cache for analytics endpoints.

Keyed by (endpoint, sorted params); invalidated wholesale when data changes
(import, snapshot, refresh). Thread-safe via a simple version counter — stale
entries are never served because every read checks the version that was
current when the entry was written.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_version: int = 0
_store: dict[tuple, tuple[int, Any]] = {}


def bump() -> None:
    """Increment the data version, logically invalidating all cached entries."""
    global _version
    with _lock:
        _version += 1
        _store.clear()


def get(key: tuple) -> Any | None:
    """Return cached value for *key* if still valid, else ``None``."""
    entry = _store.get(key)
    if entry is None:
        return None
    ver, value = entry
    if ver != _version:
        return None
    return value


def put(key: tuple, value: Any) -> None:
    """Store *value* under *key* at the current data version."""
    with _lock:
        _store[key] = (_version, value)


def cached(endpoint: str, params: dict[str, Any]):
    """Decorator that caches the return value of an analytics call.

    ``params`` values are frozen into the cache key. The decorated function
    is only called on a cache miss (or after a ``bump()``).
    """
    key = (endpoint, tuple(sorted(params.items())))
    hit = get(key)
    if hit is not None:
        return hit
    return None


def make_key(endpoint: str, **params: Any) -> tuple:
    """Build a deterministic cache key from endpoint name and params."""
    return (endpoint, tuple(sorted(params.items())))
