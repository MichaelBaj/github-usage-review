---
id: "testing-standards"
version: "1.0.0"
tags: [testing, quality, standards]
applies-to: "**/test_*"
---

# Testing Standards

## Description

Language-agnostic testing standards covering the AAA pattern, naming conventions, coverage expectations, mocking guidelines, and fixture management. Ensures tests are reliable, readable, and maintainable.

## Core Rules

1. **AAA Pattern** — Every test follows Arrange-Act-Assert. Separate each section with a blank line. One logical assertion per test (multiple `assert` calls are fine if they verify one behavior).
2. **Test Naming** — Name tests: `test_<unit>_<scenario>_<expected_result>`. Names should read as a specification. Never `test1`, `test2`, `testIt`.
3. **Coverage Expectations** — New code: 80%+ branch coverage. Critical paths (auth, payments, data mutations): 95%+. Coverage is a floor, not a ceiling.
4. **Test Independence** — Tests must not depend on execution order or shared mutable state. Each test sets up its own preconditions and cleans up after itself.
5. **Fixtures** — Use fixtures for reusable setup. Keep fixtures close to their tests. Shared fixtures in `conftest.py` (Python) or equivalent. Avoid deep fixture chains.
6. **Mocking** — Mock at boundaries (I/O, network, clock, randomness). Never mock the unit under test. Prefer fakes over mocks when behavior matters. Verify mock interactions only when the interaction *is* the behavior.
7. **Edge Cases** — Test: empty input, null/None, boundary values, maximum sizes, invalid types, concurrent access, error paths. If a bug was found, add a regression test before fixing.
8. **Test Speed** — Unit tests: < 100ms each. Integration tests: < 5s each. Slow tests get `@pytest.mark.slow` or equivalent marker. Fast feedback loop is non-negotiable.
9. **No Logic in Tests** — No conditionals, loops, or try/except in test code. Tests should be linear and obvious. If test setup is complex, extract a builder or factory.
10. **Determinism** — No flaky tests. Fix or quarantine immediately. No reliance on real time, network, or filesystem outside fixtures. Seed random generators.

## Examples

### ✅ Correct

```python
def test_load_manifest_returns_parsed_resources(tmp_path):
    """Loading a valid manifest returns the resource list."""
    # Arrange
    manifest = tmp_path / "manifest.yml"
    manifest.write_text("resources:\n  - path: skills/foo.md\n")

    # Act
    result = load_manifest(manifest)

    # Assert
    assert result["resources"][0]["path"] == "skills/foo.md"


def test_load_manifest_raises_on_missing_file():
    """Loading a nonexistent manifest raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_manifest(Path("/nonexistent/manifest.yml"))


def test_parse_frontmatter_handles_empty_tags():
    """Frontmatter with empty tags list returns empty list, not None."""
    # Arrange
    content = "---\nid: test\ntags: []\n---\n# Title"

    # Act
    fm = parse_frontmatter(content)

    # Assert
    assert fm["tags"] == []
```

### ❌ Avoid

```python
# No AAA separation, multiple behaviors, bad name
def test1():
    m = load_manifest("test.yml")
    assert m
    r = process(m)
    assert r
    save(r, "out.yml")
    assert Path("out.yml").exists()


# Logic in test — conditional makes it non-deterministic
def test_maybe():
    result = compute()
    if result > 10:
        assert result < 100
    else:
        assert result >= 0


# Mocking the unit under test
def test_bad_mock():
    with patch("mymodule.my_function") as mock:
        mock.return_value = 42
        assert my_function() == 42  # tests nothing
```

## References

- [Arrange-Act-Assert Pattern](https://wiki.c2.com/?ArrangeActAssert)
- [pytest Documentation](https://docs.pytest.org/)
- [Testing Trophy — Kent C. Dodds](https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications)
