---
id: "python-coding-standards"
version: "1.0.0"
tags: [python, quality, standards]
applies-to: "**/*.py"
---

# Python Coding Standards

## Description

Enforces PEP 8 style, strict type hints, docstrings, import ordering, testing requirements, and error handling for all Python code.

## Core Rules

1. Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants.
2. All public functions and methods MUST have type hints on every parameter and return type. Use `from __future__ import annotations` for forward refs.
3. All public functions, classes, and modules MUST have docstrings (Google style preferred).
4. Import ordering: stdlib → third-party → local, separated by blank lines. Use `isort` compatible grouping.
5. Prefer `pathlib.Path` over `os.path`. Prefer f-strings over `.format()` or `%`.
6. Use specific exceptions — never bare `except:` or `except Exception:` without re-raise.
7. All new code MUST have corresponding tests. Minimum 80% branch coverage for new modules.
8. Use dataclasses or Pydantic models for structured data — avoid raw dicts for domain objects.
9. Maximum function length: 50 lines. Extract helpers when approaching limit.
10. No mutable default arguments. Use `None` + conditional assignment pattern.

## Examples

### ✅ Correct

```python
from __future__ import annotations

from pathlib import Path

import yaml

from myproject.config import Settings


def load_manifest(path: Path) -> dict[str, list[str]]:
    """Load and parse a YAML manifest file.

    Args:
        path: Path to the manifest YAML file.

    Returns:
        Parsed manifest as a dictionary.

    Raises:
        FileNotFoundError: If manifest file does not exist.
        yaml.YAMLError: If manifest contains invalid YAML.
    """
    content = path.read_text(encoding="utf-8")
    return yaml.safe_load(content)
```

```python
from dataclasses import dataclass, field


@dataclass
class Resource:
    """A managed resource entry."""

    path: str
    resource_type: str
    description: str
    tags: list[str] = field(default_factory=list)
```

```python
def process_items(items: list[str] | None = None) -> list[str]:
    """Process items with safe default handling."""
    if items is None:
        items = []
    return [item.strip() for item in items if item]
```

### ❌ Avoid

```python
# No type hints, no docstring, bare except
def load_manifest(path):
    try:
        f = open(str(path))
        data = yaml.load(f)  # unsafe yaml.load
        f.close()
        return data
    except:
        return None
```

```python
# Mutable default argument
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags
```

```python
# Raw dict instead of dataclass, no types
def make_resource(p, t, d):
    return {"path": p, "type": t, "desc": d}
```

## References

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
