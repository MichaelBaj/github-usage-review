---
id: "security-review"
version: "1.0.0"
tags: [security, review, owasp]
applies-to: "**/*.{js,ts,py,go}"
---

# Security Review

## Description

OWASP Top 10 adapted for code review. Covers injection, authentication, authorization, data validation, secrets management, CSRF, and XSS. Applied during code review to catch security vulnerabilities before merge.

## Core Rules

1. **Injection Prevention** — Never concatenate user input into SQL, shell commands, or template strings. Use parameterized queries, prepared statements, or safe APIs.
2. **Authentication** — Verify auth checks exist on every endpoint. Use bcrypt/argon2 for password hashing. Enforce MFA where applicable. Never store plaintext credentials.
3. **Authorization** — Check permissions at the resource level, not just route level. Deny by default. Validate ownership before mutations.
4. **Input Validation** — Validate and sanitize all external input at the boundary. Whitelist over blacklist. Validate type, length, range, and format.
5. **Secrets Management** — No hardcoded secrets, API keys, or tokens in source. Use environment variables or secret managers. Audit `.gitignore` for secret file exclusion.
6. **XSS Prevention** — Escape all output rendered in HTML context. Use framework auto-escaping. Sanitize rich text with allowlists.
7. **CSRF Protection** — Use anti-CSRF tokens for state-changing operations. Verify `Origin`/`Referer` headers. Use `SameSite` cookie attribute.
8. **Sensitive Data Exposure** — Encrypt data at rest and in transit. Mask PII in logs. Use TLS 1.2+ for all connections.
9. **Dependency Security** — Pin dependency versions. Run `npm audit` / `pip audit` / `govulncheck` regularly. No dependencies with known CVEs.
10. **Error Handling** — Never expose stack traces, internal paths, or system info in error responses. Log detailed errors server-side; return generic messages to clients.

## Examples

### ✅ Correct

```python
# Parameterized query — injection safe
db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

```typescript
// Output escaping — XSS safe
const safe = DOMPurify.sanitize(userInput);
element.innerHTML = safe;
```

```python
# Secret from environment, not hardcoded
import os
api_key = os.environ["API_KEY"]
```

### ❌ Avoid

```python
# SQL injection vulnerability
db.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
```

```typescript
// XSS vulnerability — raw user input in DOM
element.innerHTML = userInput;
```

```python
# Hardcoded secret
API_KEY = "sk-abc123secretkey"
```

```python
# Stack trace exposed to client
except Exception as e:
    return {"error": str(e), "traceback": traceback.format_exc()}
```

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
