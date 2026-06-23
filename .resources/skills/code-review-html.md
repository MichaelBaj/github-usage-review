---
id: "code-review-html"
version: "1.0.0"
tags: [review, html, code-review]
applies-to: "**/*.{html,htm}"
---

# Code Review — HTML

## Purpose

High-signal review for HTML diffs. Review changed scope only. Focus: correctness, security,
reliability, compatibility, missing validation.

## Scope

- **Selectors:** `*.html`, `*.htm`
- **In scope:** templates, server-rendered pages, static documents, forms, script/style loading, accessibility-critical structure, and browser security hints
- **Out of scope:** shared guidance owned by `.resources/skills/code-review.md`

## Shared contract

- Defer shared security, tests, docs/API compatibility, anti-patterns, and output format to `.resources/skills/code-review.md`. This file adds only HTML-specific risks, validation, and examples.
- Skip formatter, lint, whitespace, naming, or import-order advice unless it hides real defect.
- Review changed lines plus directly impacted nearby context only.
- Prefer evidence-backed findings tied to concrete failure modes.

## Compact checklist

- Verify user-controlled content lands in escaped text or attribute contexts, never executable markup sinks.
- Check headings, landmarks, labels, ARIA usage, focus order, and alt text for workflows that become unusable with assistive tech.
- Inspect forms for CSRF tokens, safe methods, explicit autocomplete choices, and trustworthy action targets.
- Review scripts, styles, fonts, and images for render-blocking loads, missing `defer`, and absent lazy loading where content is offscreen.
- Flag inline scripts/styles and CSP meta changes that break hardened deployments or silently weaken policy.
- Treat meta security directives as hints only; confirm they do not replace required HTTP headers or create false assurance.

## High-risk review areas

| Risk class | What to inspect | Merge-blocking when |
|---|---|---|
| XSS in templates | Unescaped interpolation, raw HTML slots, unsafe attributes, inline event handlers | User-controlled content can execute script or inject active markup |
| Accessibility regressions | Missing labels, broken heading order, non-semantic interactive elements, incorrect ARIA | Core workflow becomes unusable or misleading for keyboard or assistive-tech users |
| Form security | Missing CSRF token, insecure GET for sensitive data, password/autofill misuse | Browser submits sensitive or state-changing data without intended protection |
| Render-path performance | Blocking scripts, eager media, synchronous third-party widgets, duplicate preloads | Page behavior depends on stalled render or degraded interactivity on first load |
| CSP compatibility | Inline code, unsafe meta relaxations, nonce/hash mismatch assumptions | Hardened deployments break or policy is silently bypassed in less trusted environments |
| Security headers via meta | `Content-Security-Policy`, `Referrer-Policy`, `X-Frame-Options` assumptions in markup | Review treats unsupported meta tags as complete protection or masks missing server headers |

## Validation expectations

| Change shape | Expected evidence | Recommended validation |
|---|---|---|
| Template or content rendering change | Proof that hostile content renders inertly and expected markup stays intact | app render/build command; targeted UI/e2e test for changed page |
| Form or auth flow change | Tests cover CSRF presence, submission method, autocomplete behavior, and server acceptance path | repo UI/integration test first; targeted form submission regression |
| Accessibility-affecting structure change | Evidence covers keyboard navigation, accessible names, and landmark/heading semantics | repo accessibility test first; targeted UI/e2e regression for changed page |
| Asset-loading or CSP-related change | Build/runtime proof shows scripts load in intended order without breaking hardened policy | repo build/e2e command; focused browser test for script loading and CSP mode |

## Deep guide (load on demand)

### XSS and escaping
- HTML review is often where server-side escaping bugs become visible even when source data came from another layer.
- Strong fixes keep untrusted data in escaped text nodes or validated safe URL contexts and avoid inline event handlers.
- Tests should include attacker-controlled text in body, attribute, and URL positions.

### Accessibility-critical semantics
- Accessibility defects are correctness defects when users cannot submit forms, read structure, or operate controls.
- Strong fixes use semantic elements first, add ARIA only to fill genuine gaps, and keep labels and focus order explicit.
- Tests should cover keyboard-only use and accessible-name expectations for changed controls.

### Form security and browser behavior
- HTML attributes influence security posture: method, action, autocomplete, and hidden token fields are runtime behavior.
- Strong fixes align form markup with server protections and avoid leaking secrets or PII into URL/query history.
- Tests should prove state-changing forms include CSRF defenses and sensitive fields do not autocomplete unintentionally.

### Render-blocking and lazy loading
- Performance issues matter in review when page correctness depends on when scripts execute or whether content becomes interactive.
- Strong fixes defer non-critical scripts, lazy-load offscreen media, and keep critical path small and ordered.
- Tests should verify page still hydrates or initializes correctly under realistic network delay.

### CSP and security header compatibility
- Meta CSP applies later and covers less than server headers; many security headers cannot be replaced by markup at all.
- Strong fixes keep header expectations documented, minimize inline code, and use nonce/hash-compatible patterns where policy is strict.
- Tests should exercise hardened deployment mode, not only permissive local dev mode.

## Examples

### Unescaped user content and inline handler
**Issue**
```html
<div class="comment">{{{comment.body}}}</div>
<a href="#" onclick="submitReply('{{comment.id}}')">Reply</a>
```

**Fix**
```html
<div class="comment">{{comment.body}}</div>
<button type="button" data-comment-id="{{comment.id}}">Reply</button>
```

**Why it matters:** Raw HTML slots and inline handlers turn user content into executable code and break CSP hardening. Validation should prove hostile comment text renders inertly and reply action still works.

### Inaccessible image link
**Issue**
```html
<a href="/reports/download">
  <img src="/static/download.png">
</a>
```

**Fix**
```html
<a href="/reports/download">
  <img src="/static/download.png" alt="Download reports">
</a>
```

**Why it matters:** Screen-reader users lose link purpose without accessible name. Validation should prove changed page exposes correct accessible name and keyboard navigation path.

### State-changing form without CSRF token
**Issue**
```html
<form action="/account/email" method="post">
  <input type="email" name="email" autocomplete="on">
  <button>Save</button>
</form>
```

**Fix**
```html
<form action="/account/email" method="post">
  <input type="hidden" name="csrf_token" value="{{csrf_token}}">
  <input type="email" name="email" autocomplete="email">
  <button type="submit">Save</button>
</form>
```

**Why it matters:** State-changing forms need explicit CSRF protection and intentional browser autofill behavior. Validation should prove submissions without token fail and valid submissions still succeed.
