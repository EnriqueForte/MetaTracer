"""Delete terminal runs and the personal data that belongs to them (TASK-30).

Watch deltas compare a new scan with historical findings of the same scope.
Pruning those runs removes them from the baseline, so a later watch can
report the same metadata as new. Pending and running scans are never deleted.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import RunActiveError, RunNotFoundError
from metatracer.db.models import RunStatus
from metatracer.db.repositories import RunRepository
from metatracer.reports.builder import run_id_short

logger = logging.getLogger("metatracer.services.retention")

_ACTIVE = frozenset({RunStatus.pending, RunStatus.running})


def delete_report_files(reports_dir: Path, run_id: str) -> int:
    """Remove exported reports whose name contains this run's short id."""
    short = run_id_short(run_id)
    if len(short) < 8 or not reports_dir.is_dir():
        return 0
    needle = f"-{short}-"
    removed = 0
    for path in reports_dir.iterdir():
        if path.is_file() and path.name.startswith("metatracer-") and needle in path.name:
            path.unlink()
            removed += 1
    return removed


async def delete_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    *,
    reports_dir: Path | None = None,
) -> None:
    """Delete one terminal run. Active scans raise :class:`RunActiveError`."""
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    if run is None:
        raise RunNotFoundError(run_id)
    if run.status in _ACTIVE:
        raise RunActiveError(run_id)
    async with session_factory() as session:
        await RunRepository(session).delete_cascade(run_id)
    if reports_dir is not None:
        delete_report_files(reports_dir, run_id)


async def prune_expired_runs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int | None,
    reports_dir: Path | None = None,
) -> list[str]:
    """Delete terminal runs started more than ``retention_days`` ago.

    ``None`` or a non-positive value keeps every run. Returns the deleted ids.
    """
    if retention_days is None or retention_days <= 0:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    async with session_factory() as session:
        old = await RunRepository(session).list_terminal_started_before(cutoff)
        ids = [run.id for run in old]
    deleted: list[str] = []
    for run_id in ids:
        try:
            await delete_run(session_factory, run_id, reports_dir=reports_dir)
        except RunActiveError:
            continue
        deleted.append(run_id)
    if deleted:
        logger.info("retention deleted %d run(s) older than %d days", len(deleted), retention_days)
    return deleted
