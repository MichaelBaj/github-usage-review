---
id: "code-review-cpp"
version: "1.0.0"
tags: [review, cpp, c-plus-plus, systems]
applies-to: "**/*.{cpp,cxx,cc,hpp,hxx}"
---

# Code Review — C++

## Purpose

High-signal review for changed C++ files. Focus: lifetime safety, ownership clarity, exception
safety, container correctness, concurrency, missing validation.

## Scope

- **Selectors:** `*.cpp`, `*.cxx`, `*.cc`, `*.hpp`, `*.hxx`
- **In scope:** RAII boundaries, constructors/destructors, smart pointers, templates, move/copy operations, STL usage, and thread/shared-state behavior
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only C++-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or include-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Prefer RAII-backed ownership; raw `new`/`delete` or manual cleanup needs explicit, provable contracts.
- Verify polymorphic bases have virtual destructors when deleted through base pointers.
- Check move/copy operations, self-assignment, and moved-from state for invariant drift.
- Review smart-pointer graphs for shared ownership leaks, aliasing confusion, and `enable_shared_from_this` misuse.
- Confirm exception safety level matches mutation pattern: no leak, no partial commit, no invalid invariant.
- Inspect iterator, reference, and pointer invalidation after STL container mutation or reallocation.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| RAII and lifetime pitfalls | constructor/destructor symmetry, stack vs heap ownership, manual cleanup in error paths | object lifetime depends on manual cleanup that can be skipped or duplicated |
| Smart pointer misuse | `unique_ptr` moves, `shared_ptr` cycles, aliasing constructors, raw pointer escape | ownership becomes ambiguous, leaks permanently, or outlives required object |
| Exception safety | state mutation around throws, allocation failure, multi-step updates, destructor behavior | throw can leak resources, leave broken invariants, or partially commit observable state |
| Move semantics errors | custom move/copy members, self-move, moved-from reuse, container relocation | moved-from object becomes unsafe to destroy or later use |
| Virtual destructor omission | base classes with virtual methods or polymorphic deletion | deleting through base pointer causes incomplete destruction or UB |
| Template instantiation issues | unconstrained templates, hidden overload selection, header-only definitions, ODR-sensitive code | valid-looking call sites fail to compile, instantiate wrong overload, or diverge across translation units |
| STL container invalidation | saved iterators/references/pointers after `push_back`, `erase`, `reserve`, rehash, splice | mutation leaves dangling references used later in changed path |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Ownership, destructor, or move/copy changes | Tests exercise construction, destruction, reassignment, and failure cleanup | project build/test target; `ctest --output-on-failure`; sanitizer-enabled run where repo supports it |
| Template or header API changes | Build evidence covers realistic instantiations and consuming targets | project build target; targeted consumer or integration build; focused unit test for changed template path |
| Container, threading, or shared-state changes | Proof from regression tests or stress tests under mutation-heavy paths | project test target; targeted integration test for changed path; ThreadSanitizer-enabled run if repo supports it |

## Deep guide (load on demand)

### RAII and lifetime design

- Strong fixes make cleanup automatic and local: constructors acquire, destructors release, and scope exit handles failure.
- Raw owning pointers, manual `close()` requirements, and hidden ownership transfer usually signal review risk.
- Watch for references or views into temporaries, object slicing, and destructors that can throw.
- Tests should cover early returns, exception paths, and destruction through public interfaces.

### Smart pointers, move semantics, and polymorphism

- `unique_ptr` ownership should move once, not be copied via `.get()` side channels.
- `shared_ptr` should represent true shared lifetime; parent/child cycles need `weak_ptr` on one edge.
- Custom move operations must leave source valid for destruction and assign destination safely on self-move.
- Base classes used polymorphically need virtual destructors even when current code seems local.

### Exception safety, templates, and containers

- Prefer strong exception safety for multi-step mutations: either commit fully or leave prior state intact.
- Template changes need evidence from real instantiations; unconstrained templates can silently accept wrong types until deep call sites.
- STL mutation frequently invalidates iterators, references, and pointers; check `vector`, `string`, `deque`, `unordered_*`, and `map::extract` behavior carefully.
- Tests should stress reallocation, erase/insert loops, alternate template argument types, and exception injection where feasible.

## Examples

### Missing virtual destructor
**Issue**
```cpp
struct Base {
    virtual void run() = 0;
};

struct Derived : Base {
    ~Derived() { close(fd_); }
    void run() override {}
    int fd_;
};
```

**Fix**
```cpp
struct Base {
    virtual ~Base() = default;
    virtual void run() = 0;
};

struct Derived : Base {
    ~Derived() override { close(fd_); }
    void run() override {}
    int fd_;
};
```

**Why it matters:** deleting `Derived` through `Base*` is undefined without virtual destruction. Validation should destroy through polymorphic interface.

### Iterator invalidation after growth
**Issue**
```cpp
std::vector<std::string> names = load_names();
auto it = names.begin();
names.push_back("new-user");
return *it;
```

**Fix**
```cpp
std::vector<std::string> names = load_names();
size_t first_index = 0;
names.push_back("new-user");
return names.at(first_index);
```

**Why it matters:** `push_back` can reallocate and dangle iterators. Validation should force container growth and read after mutation.

### Shared ownership cycle
**Issue**
```cpp
struct Node {
    std::shared_ptr<Node> parent;
    std::shared_ptr<Node> child;
};
```

**Fix**
```cpp
struct Node {
    std::weak_ptr<Node> parent;
    std::shared_ptr<Node> child;
};
```

**Why it matters:** cycles prevent destruction and hide leaks behind apparently safe smart pointers. Validation should prove nodes release after last external owner drops.
