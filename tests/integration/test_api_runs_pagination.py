"""GET /api/runs cursor pagination (TASK-21, v2.4).

Keyset pagination over ``(started_at, id)``: inserting a run between two
pages must not duplicate or drop a row, ``has_more``/``next_cursor`` are
correct, and the global ``total`` is untruncated. Uses the in-process ASGI
app the other API tests share.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import Run, RunStatus
from metatracer.db.repositories import RunRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-runs-pagination-test.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _insert_runs(
    app: FastAPI, n: int, *, status: RunStatus = RunStatus.completed
) -> list[str]:
    """Insert n runs directly through the app's own session factory."""
    async with app.state.session_factory() as session:
        repo = RunRepository(session)
        ids: list[str] = []
        for i in range(n):
            run = await repo.create(
                Run(
                    target_input=f'["http://target{i}.com"]',
                    allowed_scope='["target.com"]',
                    scope_confirmed=True,
                    status=status,
                )
            )
            ids.append(run.id)
        return ids


async def test_pagination_first_page_has_next_cursor(app, client) -> None:
    """With more rows than the limit, has_more is true and next_cursor set."""
    await _insert_runs(app, 5)
    response = await client.get("/api/runs?limit=2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5  # untruncated global count
    assert payload["has_more"] is True
    assert payload["next_cursor"] is not None
    assert len(payload["runs"]) == 2


async def test_pagination_last_page_has_no_next(app, client) -> None:
    """The final page reports has_more=False and next_cursor=None."""
    await _insert_runs(app, 4)
    response = await client.get("/api/runs?limit=4")
    payload = response.json()
    assert payload["total"] == 4
    assert payload["has_more"] is False
    assert payload["next_cursor"] is None
    assert len(payload["runs"]) == 4


async def test_pagination_walks_all_pages_without_overlap(app, client) -> None:
    """Walking next_cursor visits every run exactly once."""
    await _insert_runs(app, 7)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # hard cap against an infinite loop
        params = "limit=3" + (f"&cursor={cursor}" if cursor else "")
        response = await client.get(f"/api/runs?{params}")
        assert response.status_code == 200
        payload = response.json()
        ids = [run["run_id"] for run in payload["runs"]]
        assert not any(run_id in seen for run_id in ids)  # no duplicates
        seen.extend(ids)
        cursor = payload["next_cursor"]
        if not payload["has_more"]:
            break
    assert len(seen) == 7
    assert cursor is None


async def test_pagination_stable_under_new_insert(app, client) -> None:
    """A run inserted between page 1 and page 2 does not shift rows.

    Keyset anchors reference the last-seen (started_at, id). A new row with a
    fresh started_at lands on the NEWER side (it belongs to page 1's
    territory), so page 2 still contains exactly the rows that followed the
    anchor at page-1 time — no duplicates, no drops, no shifts.
    """
    page1_ids = await _insert_runs(app, 3)

    response = await client.get("/api/runs?limit=2")
    first_page = [run["run_id"] for run in response.json()["runs"]]
    next_cursor = response.json()["next_cursor"]

    # A new run lands between the two pages.
    fresh_ids = await _insert_runs(app, 1)

    response2 = await client.get(f"/api/runs?limit=2&cursor={next_cursor}")
    second_page = [run["run_id"] for run in response2.json()["runs"]]

    # The union covers the 3 pre-existing runs exactly once; the fresh run
    # belongs to page 1's range and is NOT pushed into page 2.
    union = first_page + second_page
    assert len(union) == len(set(union))  # no duplicates
    assert set(union) == set(page1_ids)  # all pre-existing, no drops
    assert not set(union) & set(fresh_ids)  # the fresh row did not shift in


async def test_pagination_respects_status_filter(app, client) -> None:
    """The keyset predicate composes with the status filter."""
    await _insert_runs(app, 3, status=RunStatus.completed)
    await _insert_runs(app, 2, status=RunStatus.failed)
    response = await client.get("/api/runs?status=completed&limit=2")
    payload = response.json()
    assert payload["total"] == 3  # global count respects the filter
    assert payload["has_more"] is True
    assert all(run["status"] == "completed" for run in payload["runs"])

    # The second completed page continues with only completed rows.
    response2 = await client.get(
        f"/api/runs?status=completed&limit=2&cursor={payload['next_cursor']}"
    )
    payload2 = response2.json()
    assert payload2["has_more"] is False
    assert all(run["status"] == "completed" for run in payload2["runs"])
    assert len(payload2["runs"]) == 1


async def test_pagination_malformed_cursor_is_422(app, client) -> None:
    """A cursor that is not <started_at_iso>_<run_id> is rejected with 422."""
    await _insert_runs(app, 2)
    response = await client.get("/api/runs?cursor=not-a-valid-cursor")
    assert response.status_code == 422