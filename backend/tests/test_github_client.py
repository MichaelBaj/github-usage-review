"""Tests for GitHub report download resilience."""
from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

import httpx
import pytest

from app import github_client
from app.github_client import GitHubClient


class _FakePlainClient:
    """Return predetermined report download outcomes."""

    def __init__(self, outcomes: Sequence[httpx.Response | httpx.TransportError]) -> None:
        self.outcomes = list(outcomes)
        self.attempts = 0

    async def __aenter__(self) -> _FakePlainClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def get(self, _url: str) -> httpx.Response:
        outcome = self.outcomes[self.attempts]
        self.attempts += 1
        if isinstance(outcome, httpx.TransportError):
            raise outcome
        return outcome


async def test_download_report_recovers_after_transient_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signed report download succeeds after four transient failures."""
    fake_client = _FakePlainClient(
        [
            httpx.ConnectError("temporary") for _ in range(4)
        ]
        + [
            httpx.Response(
                200,
                text="report-data",
                request=httpx.Request("GET", "https://copilot-reports.github.com/signed"),
            )
        ]
    )
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(github_client.httpx, "AsyncClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(github_client.asyncio, "sleep", fake_sleep)
    client = object.__new__(GitHubClient)

    result = await client._download_report("https://copilot-reports.github.com/signed")

    assert result == "report-data"
    assert fake_client.attempts == 5
    assert delays == [2.0, 4.0, 8.0, 16.0]


async def test_download_report_exhausts_retries_with_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent transport failure reports retry and network guidance."""
    fake_client = _FakePlainClient(
        [httpx.ConnectError("temporary") for _ in range(5)]
    )

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(github_client.httpx, "AsyncClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(github_client.asyncio, "sleep", fake_sleep)
    client = object.__new__(GitHubClient)

    with pytest.raises(httpx.ConnectError, match=r"after 5 attempts.*outbound HTTPS and DNS"):
        await client._download_report("https://copilot-reports.github.com/signed")

    assert fake_client.attempts == 5