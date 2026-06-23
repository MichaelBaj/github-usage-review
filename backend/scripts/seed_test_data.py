"""Seed the SQLite store with realistic synthetic data for UI validation.

Use this when you don't yet have a GitHub PAT with Copilot enterprise
access. Generates a coherent ~90-day history with:

  * Org + per-team Copilot metrics (matching the GitHub Metrics API shape,
    fed through the real flatteners so the flattened tables stay
    consistent with the stored raw JSON).
  * Seats split into power users / regulars / stale / never-used.
  * Teams with members.
  * Repos and pull requests with author skew toward seat-holders so the
    "AI vs non-AI" PR-correlation buckets show a credible delta.
  * Enhanced-billing ``usageItems`` for AI credits per user, so the
    AI-credit rollups populate without the real billing API.

Run::

    cd backend
    .venv/bin/python -m scripts.seed_test_data

Override the DB path with the standard ``DB_PATH`` env var, e.g.::

    DB_PATH=./data/copilot-fake.db .venv/bin/python -m scripts.seed_test_data
"""

from __future__ import annotations

import json
import os
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

# Ensure the seed DB lives in a writable location when run outside docker.
os.environ.setdefault("DB_PATH", os.path.abspath("data/copilot.db"))
# Avoid pydantic-settings demanding a real PAT just to import config.
os.environ.setdefault("GITHUB_TOKEN", "fake-seed-token")

from app import db  # noqa: E402  (import after env defaults)
from app.config import BILLING_MIN_DATE  # noqa: E402
from app.snapshot import (  # noqa: E402
    _flatten_billing_usage,
    _flatten_editors,
    _flatten_languages,
    _flatten_models,
)

RNG = random.Random(20260604)

DAYS_OF_HISTORY = 90
_BILLING_MIN = date.fromisoformat(BILLING_MIN_DATE)
PR_HISTORY_DAYS = 120

TEAMS: list[dict[str, Any]] = [
    {"slug": "platform", "name": "Platform", "size": 14, "intensity": 1.4},
    {"slug": "data", "name": "Data Engineering", "size": 9, "intensity": 1.1},
    {"slug": "frontend", "name": "Frontend", "size": 11, "intensity": 1.25},
    {"slug": "security", "name": "Security", "size": 6, "intensity": 0.7},
    {"slug": "sre", "name": "SRE", "size": 8, "intensity": 1.0},
    {"slug": "qa", "name": "Quality Assurance", "size": 7, "intensity": 0.6},
]

EDITORS = ["vscode", "jetbrains", "neovim"]
EDITOR_WEIGHTS = [0.65, 0.25, 0.10]
MODELS = ["gpt-4o", "claude-3.5-sonnet", "o1-mini", "default"]
MODEL_WEIGHTS = [0.50, 0.30, 0.15, 0.05]
CHAT_MODELS = ["gpt-4o", "claude-3.5-sonnet"]
LANGUAGES = [
    ("python", 0.30),
    ("typescript", 0.25),
    ("go", 0.15),
    ("java", 0.10),
    ("rust", 0.08),
    ("yaml", 0.07),
    ("markdown", 0.05),
]

REPOS = [
    "platform-core",
    "platform-api",
    "data-pipelines",
    "data-warehouse",
    "frontend-web",
    "frontend-mobile",
    "security-scanner",
    "security-policies",
    "sre-runbooks",
    "sre-terraform",
    "qa-automation",
    "shared-libs",
]


# ---------------------------------------------------------------------------
# user / team generation
# ---------------------------------------------------------------------------


def _make_users() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Build seats + team membership.

    Returns:
        ``(seats_rows, team_to_members)`` where ``seats_rows`` are
        ready-to-write rows for ``db.replace_seats`` and the dict maps
        team slug to member logins (some members may have no seat).
    """
    now = datetime.now(UTC)
    seats: list[dict[str, Any]] = []
    team_members: dict[str, list[str]] = {t["slug"]: [] for t in TEAMS}

    user_counter = 1
    for team in TEAMS:
        size = team["size"]
        # Mix per team: ~70% have seats, of those 20% power / 60% regular /
        # 15% stale / 5% never-used. Remainder (no seat) shows up in PR
        # correlation as the non-AI bucket.
        for _ in range(size):
            login = f"user{user_counter:03d}"
            user_counter += 1
            team_members[team["slug"]].append(login)

            has_seat = RNG.random() < 0.75
            if not has_seat:
                continue

            cohort = RNG.random()
            if cohort < 0.18:
                kind = "power"
            elif cohort < 0.78:
                kind = "regular"
            elif cohort < 0.93:
                kind = "stale"
            else:
                kind = "never"

            created_days_ago = RNG.randint(30, 360)
            created_at = (now - timedelta(days=created_days_ago)).isoformat()

            if kind == "never":
                last_activity = None
                editor = None
            elif kind == "stale":
                last_activity = (now - timedelta(days=RNG.randint(45, 120))).isoformat()
                editor = RNG.choice(EDITORS)
            else:
                last_activity = (now - timedelta(hours=RNG.randint(1, 96))).isoformat()
                editor = RNG.choice(EDITORS)

            seats.append(
                {
                    "login": login,
                    "team": team["slug"],
                    "assigning_team": team["name"],
                    "created_at": created_at,
                    "updated_at": now.isoformat(),
                    "last_activity_at": last_activity,
                    "last_activity_editor": editor,
                    "pending_cancellation_date": None,
                    "plan_type": "business",
                    "raw_json": json.dumps(
                        {
                            "assignee": {"login": login},
                            "assigning_team": {"slug": team["slug"], "name": team["name"]},
                            "created_at": created_at,
                            "last_activity_at": last_activity,
                            "last_activity_editor": editor,
                            "plan_type": "business",
                        }
                    ),
                }
            )
    return seats, team_members


# ---------------------------------------------------------------------------
# org / team metrics
# ---------------------------------------------------------------------------


def _weighted_sample(items: list, weights: list[float], k: int) -> list:
    """Sample ``k`` distinct items by weight (sampling without replacement)."""
    pool = list(zip(items, weights, strict=True))
    out = []
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        r = RNG.uniform(0, total)
        upto = 0.0
        for i, (item, w) in enumerate(pool):
            upto += w
            if upto >= r:
                out.append(item)
                pool.pop(i)
                break
    return out


def _build_day_payload(day: date, engaged_users: int, intensity: float) -> dict[str, Any]:
    """Build a GitHub Metrics API-shaped payload for ``day``.

    ``intensity`` scales volumes — 1.0 ≈ baseline, >1 = heavier usage.
    """
    # weekday-based engagement drop on weekends
    weekday_mult = 0.35 if day.weekday() >= 5 else 1.0
    base = max(1, int(engaged_users * weekday_mult))

    code_editors = []
    chat_editors = []
    for editor, eweight in zip(EDITORS, EDITOR_WEIGHTS, strict=True):
        editor_engaged = max(1, int(base * eweight))
        # Pick 2 models per editor most days
        active_models = _weighted_sample(MODELS, MODEL_WEIGHTS, k=2)
        code_models_payload = []
        for model in active_models:
            langs = _weighted_sample(
                [l for l, _ in LANGUAGES], [w for _, w in LANGUAGES], k=4
            )
            lang_payload = []
            for lang in langs:
                lang_weight = dict(LANGUAGES)[lang]
                volume = max(
                    1,
                    int(editor_engaged * intensity * lang_weight * RNG.uniform(80, 140)),
                )
                # ~30% acceptance rate, ~3 lines per acceptance
                acceptances = int(volume * RNG.uniform(0.22, 0.36))
                lines_suggested = int(volume * RNG.uniform(2.8, 3.4))
                lines_accepted = int(acceptances * RNG.uniform(2.5, 3.1))
                lang_payload.append(
                    {
                        "name": lang,
                        "total_code_suggestions": volume,
                        "total_code_acceptances": acceptances,
                        "total_code_lines_suggested": lines_suggested,
                        "total_code_lines_accepted": lines_accepted,
                        "total_engaged_users": max(1, int(editor_engaged * lang_weight)),
                    }
                )
            code_models_payload.append(
                {
                    "name": model,
                    "is_custom_model": False,
                    "total_engaged_users": editor_engaged,
                    "languages": lang_payload,
                }
            )
        code_editors.append(
            {
                "name": editor,
                "total_engaged_users": editor_engaged,
                "models": code_models_payload,
            }
        )

        # Chat: subset of code volume, only a couple of models
        chat_models_payload = []
        for model in CHAT_MODELS:
            chats = max(1, int(editor_engaged * intensity * RNG.uniform(2, 6)))
            chat_models_payload.append(
                {
                    "name": model,
                    "is_custom_model": False,
                    "total_engaged_users": max(1, int(editor_engaged * 0.7)),
                    "total_chats": chats,
                    "total_chat_insertion_events": int(chats * RNG.uniform(0.15, 0.30)),
                    "total_chat_copy_events": int(chats * RNG.uniform(0.05, 0.15)),
                }
            )
        chat_editors.append(
            {
                "name": editor,
                "total_engaged_users": max(1, int(editor_engaged * 0.7)),
                "models": chat_models_payload,
            }
        )

    return {
        "date": day.isoformat(),
        "total_active_users": int(engaged_users * weekday_mult * 1.2),
        "total_engaged_users": base,
        "copilot_ide_code_completions": {
            "editors": code_editors,
            "languages": [],  # we keep detail under editors only; matches real API shape
        },
        "copilot_ide_chat": {
            "editors": chat_editors,
        },
    }


def _seed_metrics(seats: list[dict[str, Any]], team_members: dict[str, list[str]]) -> None:
    """Generate ``DAYS_OF_HISTORY`` days of org + team metrics."""
    today = datetime.now(UTC).date()
    seat_logins = {s["login"] for s in seats}
    # only seat-holders count toward engaged-users base
    engaged_org_base = max(5, len(seat_logins))

    for offset in range(DAYS_OF_HISTORY):
        day = today - timedelta(days=offset + 1)
        # Slight growth trend backward in time → fewer users older days
        growth_factor = 1.0 - (offset / (DAYS_OF_HISTORY * 2.5))
        org_engaged = max(5, int(engaged_org_base * growth_factor * RNG.uniform(0.85, 1.05)))
        org_payload = _build_day_payload(day, org_engaged, intensity=1.0)

        db.upsert_org_day(
            date=day.isoformat(),
            total_active=org_payload["total_active_users"],
            total_engaged=org_payload["total_engaged_users"],
            raw=org_payload,
        )
        db.replace_language_rows(day.isoformat(), _flatten_languages(org_payload))
        db.replace_editor_rows(day.isoformat(), _flatten_editors(org_payload))
        db.replace_model_rows(day.isoformat(), "org", "", _flatten_models(org_payload))

        for team in TEAMS:
            team_seat_members = [
                m for m in team_members[team["slug"]] if m in seat_logins
            ]
            if not team_seat_members:
                continue
            team_engaged = max(1, int(len(team_seat_members) * growth_factor))
            team_payload = _build_day_payload(day, team_engaged, intensity=team["intensity"])
            db.upsert_team_day(
                date=day.isoformat(),
                team_slug=team["slug"],
                total_active=team_payload["total_active_users"],
                total_engaged=team_payload["total_engaged_users"],
                raw=team_payload,
            )
            db.replace_team_language_rows(
                day.isoformat(), team["slug"], _flatten_languages(team_payload)
            )
            db.replace_model_rows(
                day.isoformat(), "team", team["slug"], _flatten_models(team_payload)
            )


# ---------------------------------------------------------------------------
# repos + pull requests
# ---------------------------------------------------------------------------


def _seed_repos_and_prs(
    seats: list[dict[str, Any]],
    team_members: dict[str, list[str]],
) -> None:
    """Generate repos + PRs over ``PR_HISTORY_DAYS`` days.

    Authors are weighted toward seat-holders (so the "AI bucket" of
    PR-correlation gets the majority of activity) and within seat-holders
    biased toward a small set of power authors.
    """
    now = datetime.now(UTC)
    repos = [
        {
            "name": r,
            "full_name": f"Juniper-SSN/{r}",
            "archived": 0,
            "fork": 0,
            "default_branch": "main",
            "updated_at": now.isoformat(),
        }
        for r in REPOS
    ]
    db.replace_repos(repos)

    seat_logins = [s["login"] for s in seats if s.get("last_activity_at")]
    non_seat_authors = []
    # Generate non-seat author pool: members in team_members but not in seats
    all_members = {m for members in team_members.values() for m in members}
    seat_set = {s["login"] for s in seats}
    non_seat_authors = sorted(all_members - seat_set)

    # Power-author bias: top 15% of seat-holders write ~50% of PRs
    seat_power = RNG.sample(seat_logins, max(1, len(seat_logins) // 7))

    prs: list[dict[str, Any]] = []
    pr_number_by_repo: dict[str, int] = {r: 0 for r in REPOS}

    for offset in range(PR_HISTORY_DAYS):
        day = now - timedelta(days=offset + 1)
        # 6–18 PRs per day weekday, less on weekends
        weekday = day.weekday()
        daily_count = RNG.randint(2, 6) if weekday >= 5 else RNG.randint(6, 18)
        for _ in range(daily_count):
            repo = RNG.choice(REPOS)
            pr_number_by_repo[repo] += 1

            roll = RNG.random()
            if roll < 0.55:
                author = RNG.choice(seat_power)
            elif roll < 0.85 and seat_logins:
                author = RNG.choice(seat_logins)
            elif non_seat_authors:
                author = RNG.choice(non_seat_authors)
            else:
                author = RNG.choice(seat_logins) if seat_logins else "unknown"

            is_seat = author in seat_set
            # Seat holders push smaller, faster PRs more often
            if is_seat:
                additions = max(1, int(RNG.expovariate(1 / 110)))
                deletions = max(0, int(RNG.expovariate(1 / 35)))
                cycle_hours = RNG.uniform(2, 40)
                merge_chance = 0.83
                review_comments = RNG.randint(0, 5)
            else:
                additions = max(1, int(RNG.expovariate(1 / 220)))
                deletions = max(0, int(RNG.expovariate(1 / 70)))
                cycle_hours = RNG.uniform(8, 96)
                merge_chance = 0.70
                review_comments = RNG.randint(0, 9)

            created_at = day - timedelta(hours=RNG.uniform(0, 24))
            merged = RNG.random() < merge_chance
            if merged:
                merged_at = created_at + timedelta(hours=cycle_hours)
                if merged_at > now:
                    merged_at = now - timedelta(minutes=15)
                state = "merged"
                closed_at = merged_at
            else:
                merged_at = None
                state = "closed" if RNG.random() < 0.5 else "open"
                closed_at = (
                    (created_at + timedelta(hours=RNG.uniform(4, 72)))
                    if state == "closed"
                    else None
                )

            prs.append(
                {
                    "repo": repo,
                    "number": pr_number_by_repo[repo],
                    "author": author,
                    "state": state,
                    "created_at": created_at.isoformat(),
                    "merged_at": merged_at.isoformat() if merged_at else None,
                    "closed_at": closed_at.isoformat() if closed_at else None,
                    "additions": additions,
                    "deletions": deletions,
                    "changed_files": max(1, additions // 80),
                    "comments": RNG.randint(0, 6),
                    "review_comments": review_comments,
                    "commits": max(1, RNG.randint(1, 8)),
                    "title": f"{repo}: change #{pr_number_by_repo[repo]}",
                    "base_ref": "main",
                    "head_ref": f"feat/{author}-{pr_number_by_repo[repo]}",
                }
            )

    db.upsert_pull_requests(prs)


# ---------------------------------------------------------------------------
# billing usage (AI credits)
# ---------------------------------------------------------------------------


def _seed_billing_usage(seats: list[dict[str, Any]]) -> None:
    """Build enhanced-billing ``usageItems`` for AI credits + a copilot seat SKU.

    Lots of small per-user per-day rows so the by-user rollups have a clear shape.
    SKUs encode the model name so the per-user "Model usage" panel has signal.
    """
    today = datetime.now(UTC).date()
    items: list[dict[str, Any]] = []

    active_seats = [s for s in seats if s.get("last_activity_at")]

    # Realistic premium-request SKUs surfaced by GitHub's enhanced billing API.
    # Each user gets a personal mix so the model breakdown varies by user.
    # NOTE: SKU strings kept as-is — they match real GitHub API output.
    models = [
        "Claude 3.5 Sonnet",
        "Claude 3.7 Sonnet",
        "GPT-4.1",
        "GPT-4o",
        "o3-mini",
        "Gemini 2.5 Pro",
    ]

    def _model_mix(login: str) -> list[tuple[str, float]]:
        """Deterministic per-user weighting across the model menu."""
        seed_val = sum(ord(c) for c in login)
        local_rng = random.Random(seed_val)
        weights = [local_rng.random() ** 2 for _ in models]
        # Force every user to lean on 1-3 favorite models
        favorites = local_rng.sample(range(len(models)), k=local_rng.randint(1, 3))
        for idx in favorites:
            weights[idx] += local_rng.uniform(1.5, 3.5)
        total = sum(weights) or 1.0
        return [(m, w / total) for m, w in zip(models, weights)]

    for offset in range(DAYS_OF_HISTORY):
        day = today - timedelta(days=offset + 1)
        if day < _BILLING_MIN:
            continue
        # AI-credit usage skews toward chat-heavy power users
        for seat in active_seats:
            login = seat["login"]
            # 60% of active seats record AI credits on a given weekday
            weekday_mult = 0.35 if day.weekday() >= 5 else 1.0
            if RNG.random() > 0.55 * weekday_mult:
                continue
            # most users: 3-25 AI credits/day; power users: 30-90
            is_power = (hash(login) % 7) == 0
            qty_total = (
                RNG.randint(30, 90) if is_power else RNG.randint(3, 25)
            )
            qty_total = max(1, int(qty_total * weekday_mult))

            # Spread the day's requests across the user's model mix.
            mix = _model_mix(login)
            remaining = qty_total
            for model, share in mix[:-1]:
                share_qty = int(round(qty_total * share))
                if share_qty <= 0:
                    continue
                share_qty = min(share_qty, remaining)
                remaining -= share_qty
                if share_qty == 0:
                    continue
                net = round(share_qty * 0.04, 2)
                items.append(
                    {
                        "date": day.isoformat(),
                        "username": login,
                        "product": "Copilot",
                        "sku": f"Copilot Premium Request - {model}",
                        "unitType": "request",
                        "quantity": share_qty,
                        "grossAmount": net,
                        "discountAmount": 0,
                        "netAmount": net,
                        "repositoryName": "",
                    }
                )
            if remaining > 0:
                model = mix[-1][0]
                net = round(remaining * 0.04, 2)
                items.append(
                    {
                        "date": day.isoformat(),
                        "username": login,
                        "product": "Copilot",
                        "sku": f"Copilot Premium Request - {model}",
                        "unitType": "request",
                        "quantity": remaining,
                        "grossAmount": net,
                        "discountAmount": 0,
                        "netAmount": net,
                        "repositoryName": "",
                    }
                )

        # also a daily seat-cost row at org scope so SKU breakdown is non-trivial
        items.append(
            {
                "date": day.isoformat(),
                "username": "",
                "product": "Copilot",
                "sku": "Copilot Business User",
                "unitType": "user_day",
                "quantity": len(active_seats),
                "grossAmount": round(len(active_seats) * (39.0 / 30.0), 2),
                "discountAmount": 0,
                "netAmount": round(len(active_seats) * (39.0 / 30.0), 2),
                "repositoryName": "",
            }
        )

    db.replace_billing_usage(_flatten_billing_usage({"usageItems": items}))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Drop all data and re-seed the DB end-to-end."""
    print(f"[seed] DB_PATH = {os.environ['DB_PATH']}")
    db.init_db()

    # Wipe everything we manage so re-runs are deterministic.
    with db.connect() as conn:
        for table in (
            "daily_org_metrics",
            "daily_team_metrics",
            "daily_language_metrics",
            "daily_editor_metrics",
            "daily_model_metrics",
            "daily_team_language_metrics",
            "seats",
            "team_members",
            "repos",
            "pull_requests",
            "billing_usage",
            "meta",
        ):
            conn.execute(f"DELETE FROM {table}")

    print("[seed] generating users + teams …")
    seats, team_members = _make_users()
    db.replace_seats(seats)
    for slug, members in team_members.items():
        db.replace_team_members(slug, members)

    print(f"[seed] seeded {len(seats)} seats across {len(TEAMS)} teams")

    print(f"[seed] generating {DAYS_OF_HISTORY} days of org + team metrics …")
    _seed_metrics(seats, team_members)

    print(f"[seed] generating {PR_HISTORY_DAYS} days of PRs …")
    _seed_repos_and_prs(seats, team_members)

    print(f"[seed] generating {DAYS_OF_HISTORY} days of billing usage …")
    _seed_billing_usage(seats)

    db.set_meta("last_snapshot_at", datetime.now(UTC).isoformat())
    db.set_meta("seed_mode", "true")

    with db.connect() as conn:
        counts = {
            t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            for t in (
                "daily_org_metrics",
                "daily_team_metrics",
                "daily_language_metrics",
                "daily_editor_metrics",
                "daily_model_metrics",
                "daily_team_language_metrics",
                "seats",
                "team_members",
                "repos",
                "pull_requests",
                "billing_usage",
            )
        }
    print("[seed] done. row counts:")
    for table, n in counts.items():
        print(f"   {table:36s} {n:>7}")
    print()
    print("[seed] Next steps:")
    print("[seed]   1. export SEED_MODE=true")
    print("[seed]      (prevents the boot snapshot from overwriting this data)")
    print(f"[seed]   2. export DB_PATH={os.environ['DB_PATH']}")
    print("[seed]   3. start the backend, e.g.:")
    print("[seed]        .venv/bin/python -m uvicorn app.main:app --port 8000 --reload")
    print("[seed]   4. start the frontend (`cd frontend && npm run dev`) and open the UI")


if __name__ == "__main__":
    main()
