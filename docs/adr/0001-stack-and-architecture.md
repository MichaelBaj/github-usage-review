# ADR-0001: Stack and Architecture

## Status

Accepted — 2026-06-04

## Context

We need an internal tool that lets an executive team review GitHub
Copilot usage across the `Juniper-SSN` org over a 3-month window and
make decisions on adoption, ROI, and seat right-sizing. Constraints:

- Must use GitHub's official Copilot admin APIs (token-based, admin
  scopes already available).
- GitHub Copilot Metrics API only retains the last 28 days, so we must
  accumulate history locally to reach a 90-day exec view.
- Single-tenant, internal use; will run containerized.
- Maintainer is comfortable with Python.

## Decision

| Concern | Choice |
|---------|--------|
| Backend | Python 3.12 + FastAPI + httpx + APScheduler |
| Storage | SQLite (file-backed, mounted volume) |
| Frontend | React 18 + Vite + TypeScript (strict) + Recharts |
| Packaging | Two Docker images, orchestrated by Docker Compose |
| Reverse Proxy | Nginx in the frontend image, proxying `/api` to the backend service |
| Snapshot Strategy | Daily APScheduler job + opportunistic on-startup pull, idempotent upserts by date |
| Config | Environment variables via Pydantic Settings |
| Tests | pytest with temp-SQLite fixture |
| Lint / Format | Ruff |
| Type Checking | mypy (strict) |

## Consequences

**Positive**

- FastAPI gives async I/O, OpenAPI docs, and Pydantic validation in one package.
- SQLite removes operational overhead and keeps the whole app a single
  compose file — fine for the data volume (≤ 100s of MB even after a year).
- Idempotent date-keyed upserts mean re-running snapshots is safe and
  recovers gracefully from missed runs.
- Containerized layout makes it portable from a laptop to an internal VM
  with no code changes.

**Negative**

- SQLite limits us to one writer process; not an issue for a single
  scheduled job, but a future need for parallel writers would require a
  migration to Postgres.
- The first 28 days of recorded history come from a single API pull —
  if the tool is wiped, history is lost until 28 more days accumulate.
- No built-in auth on the dashboard; we rely on network placement or an
  external reverse proxy.

## Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| Node.js (Express) backend | Same capability, but pulled-in JS ecosystem fragmentation; Python keeps a single language for analytics. |
| Plain HTML + Chart.js (no build) | Faster bootstrap but harder to extend with typed components and the executive UI is already non-trivial. |
| Postgres from day one | Operational overhead unjustified for a single-tenant tool at this data volume. |
| GitHub-hosted dashboards / Insights | Don't aggregate Copilot metrics with the cost + stale-seat insights we need. |
| Building on top of an existing observability stack (Grafana on Prometheus) | Heavy for a single dashboard and Prometheus is a poor fit for low-frequency daily snapshots. |

## References

- [GitHub Copilot Metrics API](https://docs.github.com/en/rest/copilot/copilot-metrics)
- [GitHub Copilot User Management API](https://docs.github.com/en/rest/copilot/copilot-user-management)

---

*Last reviewed: 2026-06-04*
