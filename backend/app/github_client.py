"""Thin async wrapper for the GitHub Copilot admin APIs.

Endpoints used:

* ``GET /orgs/{org}/copilot/metrics`` — last 28 days, daily aggregates
* ``GET /orgs/{org}/team/{team_slug}/copilot/metrics`` — per-team
* ``GET /orgs/{org}/copilot/billing/seats`` — paginated
* ``GET /orgs/{org}/teams`` — paginated

See https://docs.github.com/en/rest/copilot for full reference.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import settings

GITHUB_API = "https://api.github.com"
ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"


class SnapshotPreflightError(RuntimeError):
    """Raised when snapshot prerequisites are not met before ingestion."""


class GitHubClient:
    """Authenticated async client for the GitHub REST API."""

    def __init__(
        self,
        token: str | None = None,
        org: str | None = None,
        enterprise: str | None = None,
    ) -> None:
        """Build the client.

        Args:
            token: GitHub PAT. Falls back to ``settings.github_token``.
            org: Org login. Falls back to ``settings.github_org``.
            enterprise: Enterprise slug for org-metrics fallback. Falls back
                to ``settings.github_enterprise``.

        Raises:
            RuntimeError: If no token is configured.
        """
        self.token = token or settings.github_token
        self.org = org or settings.github_org
        self.enterprise = enterprise if enterprise is not None else settings.github_enterprise
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is not set")
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            timeout=30.0,
            headers={
                "Accept": ACCEPT,
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "copilot-usage-review/0.1",
            },
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Issue a GET; raises on non-2xx."""
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response

    async def _paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate over a paginated endpoint until exhausted."""
        page = 1
        per_page = 100
        while True:
            page_params: dict[str, Any] = {"per_page": per_page, "page": page, **(params or {})}
            response = await self._get(path, params=page_params)
            data = response.json()
            # Seats endpoint returns {"total_seats": N, "seats": [...]}
            items = data.get("seats") if isinstance(data, dict) and "seats" in data else data
            if not items:
                break
            for item in items:
                yield item
            if len(items) < per_page:
                break
            page += 1

    # ----- Copilot metrics -----

    async def org_metrics(self) -> list[dict[str, Any]]:
        """Return org-level Copilot metrics for the last 28 days.

        Enterprise-managed orgs return 404 on the org endpoint when metrics
        are surfaced only at the enterprise tier. When ``github_enterprise``
        is configured, fall back to ``/enterprises/{ent}/copilot/metrics``.
        """
        try:
            response = await self._get(f"/orgs/{self.org}/copilot/metrics")
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and self.enterprise:
                response = await self._get(
                    f"/enterprises/{self.enterprise}/copilot/metrics"
                )
                return response.json()
            raise

    async def team_metrics(self, team_slug: str) -> list[dict[str, Any]]:
        """Return Copilot metrics for ``team_slug`` for the last 28 days."""
        response = await self._get(f"/orgs/{self.org}/team/{team_slug}/copilot/metrics")
        return response.json()

    # ----- Seats -----

    async def list_seats(self) -> list[dict[str, Any]]:
        """Return all Copilot seat assignments for the org."""
        return [s async for s in self._paginate(f"/orgs/{self.org}/copilot/billing/seats")]

    # ----- Teams -----

    async def list_teams(self) -> list[dict[str, Any]]:
        """Return all teams in the org."""
        return [t async for t in self._paginate(f"/orgs/{self.org}/teams")]

    async def list_team_members(self, team_slug: str) -> list[dict[str, Any]]:
        """Return all members of ``team_slug``."""
        return [
            m
            async for m in self._paginate(
                f"/orgs/{self.org}/teams/{team_slug}/members"
            )
        ]

    # ----- Repos / Pull Requests -----

    async def list_org_repos(self) -> list[dict[str, Any]]:
        """Return all repos in the org (one request page at a time)."""
        return [r async for r in self._paginate(f"/orgs/{self.org}/repos", {"type": "all", "sort": "pushed"})]

    async def list_repo_pulls(
        self,
        repo: str,
        state: str = "all",
        since_iso: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream PRs for ``repo`` newest-first; stop early when older than ``since_iso``.

        GitHub list-PRs endpoint sorts by ``created`` descending by default,
        which lets us bail as soon as we cross the lookback boundary.
        """
        params = {"state": state, "sort": "created", "direction": "desc"}
        page = 1
        per_page = 100
        while True:
            response = await self._get(
                f"/repos/{self.org}/{repo}/pulls",
                params={"per_page": per_page, "page": page, **params},
            )
            items = response.json()
            if not items:
                return
            for pr in items:
                if since_iso and (pr.get("created_at") or "") < since_iso:
                    return
                yield pr
            if len(items) < per_page:
                return
            page += 1

    async def get_pull_request(self, repo: str, number: int) -> dict[str, Any]:
        """Fetch full PR detail (needed for additions/deletions/changed_files)."""
        response = await self._get(f"/repos/{self.org}/{repo}/pulls/{number}")
        return response.json()

    # ----- Enhanced Billing usage (AI credits + other SKUs) -----

    async def org_billing_usage(
        self,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
    ) -> dict[str, Any]:
        """Fetch enhanced billing usage for the org.

        Endpoint: ``GET /organizations/{org}/settings/billing/usage``.

        Returns the raw API payload (``{"usageItems": [...]}``). Per-SKU
        line items include ``product``, ``sku``, ``unitType``, ``quantity``,
        ``grossAmount``, ``netAmount``, ``usageAt``, ``repositoryName``,
        and (where attributable) ``username`` — which is how we surface
        Copilot AI-credit usage per user.

        Requires a token with the ``read:enterprise`` or
        ``Plan: Read`` (admin:org for legacy) permission. Some org tiers
        return 403 — caller should handle gracefully.
        """
        params: dict[str, Any] = {}
        if year is not None:
            params["year"] = year
        if month is not None:
            params["month"] = month
        if day is not None:
            params["day"] = day
        if hour is not None:
            params["hour"] = hour
        response = await self._get(
            f"/organizations/{self.org}/settings/billing/usage",
            params=params or None,
        )
        return response.json()

    async def enterprise_billing_usage(
        self,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
    ) -> dict[str, Any]:
        """Fetch enhanced billing usage at the enterprise scope (fallback)."""
        if not self.enterprise:
            raise RuntimeError("github_enterprise is not configured")
        params: dict[str, Any] = {}
        if year is not None:
            params["year"] = year
        if month is not None:
            params["month"] = month
        if day is not None:
            params["day"] = day
        if hour is not None:
            params["hour"] = hour
        response = await self._get(
            f"/enterprises/{self.enterprise}/settings/billing/usage",
            params=params or None,
        )
        return response.json()

    async def assert_snapshot_permissions(self, include_pr_checks: bool = False) -> None:
        """Fail fast when token/org permissions are insufficient for snapshot refresh.

        This preflight runs cheap probe calls first so we avoid running the full
        snapshot and failing deep into high-volume API loops.
        """

        failures: list[str] = []

        def _action_for(status: int) -> str:
            if status == 401:
                return (
                    "Action: set GITHUB_TOKEN to a valid, non-expired PAT and restart backend."
                )
            if status == 403:
                return (
                    "Action: use a token authorized for org admin-level Copilot access, "
                    "grant read:org, and approve token for SSO if org enforces SAML."
                )
            if status == 404:
                return (
                    "Action: verify GITHUB_ORG / GITHUB_ENTERPRISE values and confirm "
                    "org has Copilot Business or Enterprise enabled."
                )
            return "Action: verify token and organization settings, then retry."

        async def _probe(label: str, path: str, params: dict[str, Any] | None = None) -> None:
            try:
                await self._get(path, params=params)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                failures.append(
                    f"- {label} failed ({status}) at GET {path}. {_action_for(status)}"
                )

        await _probe("Token auth check", "/user")
        await _probe(
            "Copilot seats access",
            f"/orgs/{self.org}/copilot/billing/seats",
            params={"per_page": 1, "page": 1},
        )
        await _probe(
            "Organization teams access",
            f"/orgs/{self.org}/teams",
            params={"per_page": 1, "page": 1},
        )

        # Metrics can legitimately 404 when org telemetry is below privacy
        # thresholds. We only fail for explicit auth/permission errors.
        try:
            await self._get(f"/orgs/{self.org}/copilot/metrics")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404 and self.enterprise:
                await _probe(
                    "Enterprise Copilot metrics access",
                    f"/enterprises/{self.enterprise}/copilot/metrics",
                )
            elif status in (401, 403):
                failures.append(
                    "- Copilot metrics access failed "
                    f"({status}) at GET /orgs/{self.org}/copilot/metrics. "
                    f"{_action_for(status)}"
                )

        if include_pr_checks:
            await _probe(
                "Organization repository listing access",
                f"/orgs/{self.org}/repos",
                params={"type": "all", "sort": "pushed", "per_page": 1, "page": 1},
            )

        if failures:
            raise SnapshotPreflightError(
                "Snapshot preflight failed due to GitHub token/org permission issues:\n"
                + "\n".join(failures)
            )
