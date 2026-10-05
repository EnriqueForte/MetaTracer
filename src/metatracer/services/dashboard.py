"""Dashboard aggregation service (TASK-11, v2.0).

Read-only composition over :class:`DashboardRepository`. The endpoint
``GET /api/stats`` and the ``/dashboard`` page share this one builder, so
there is exactly one definition of the dashboard model — like the CLI/Web UI
share the orchestrator. No writes happen anywhere in this module.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.repositories import (
    _FINDING_TYPE_ORDER,
    _SEVERITY_ORDER,
    DashboardRepository,
)

_DASHBOARD_TOP_LIMIT = 10
# Days of severity history shown on the dashboard (TASK-35).
TREND_DAYS = 30


class DashboardStats(BaseModel):
    """One dashboard snapshot: KPIs + breakdowns + top lists + agent usage.

    Enum values stay lowercase on the wire (data contract); ``unclassified``
    is the presentation bucket for findings with ``severity=None`` and is
    never an enum value itself.
    """

    runs: dict[str, int]  # {"total": N, **by_status}
    assets: dict[str, int]  # {"total": N, "with_issues": M}
    findings: dict[str, Any]  # total + severity_breakdown + by_type + unclassified
    top_domains: list[dict[str, Any]]  # [{"domain": str, "count": int}]
    # [{"signature", "evidence_snippet", "finding_type", "occurrences"}]
    top_evidence: list[dict[str, Any]]
    # calls, prompt_tokens, completion_tokens, total_tokens, latency_ms
    agent_usage: dict[str, int]
    # One point per UTC day, oldest first, zeros included (TASK-35).
    trends: list[dict[str, Any]] = []


def build_trends(
    rows: list[tuple[str, str | None, int]], today: datetime, days: int = TREND_DAYS
) -> list[dict[str, Any]]:
    """Fill a fixed window of days so the chart never skips an empty day."""
    start = (today - timedelta(days=days - 1)).date()
    points: dict[str, dict[str, Any]] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        points[day] = {"date": day, **{key: 0 for key in _SEVERITY_ORDER}, "unclassified": 0}
    for day, severity, count in rows:
        point = points.get(day)
        if point is None:
            continue
        point[severity if severity in _SEVERITY_ORDER else "unclassified"] += count
    return list(points.values())


def _ordered_counter(
    counter: Counter[str], canonical_order: list[str], include_unclassified: bool = False
) -> dict[str, int]:
    """Render a Counter in the canonical report order (zeros included)."""
    result: dict[str, int] = {}
    for key in canonical_order:
        result[key] = int(counter.get(key, 0))
    if include_unclassified:
        result["unclassified"] = 0  # filled by the caller from summary()
    return result


class DashboardStatsService:
    """Builds one :class:`DashboardStats` from the persisted rows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def build(self, now: datetime | None = None) -> DashboardStats:
        today = now or datetime.now(UTC)
        since = (today - timedelta(days=TREND_DAYS - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with self._session_factory() as session:
            repo = DashboardRepository(session)
            summary = await repo.summary()
            top_domains = await repo.top_domains(_DASHBOARD_TOP_LIMIT)
            top_evidence = await repo.top_evidence(_DASHBOARD_TOP_LIMIT)
            agent_usage = await repo.agent_usage()
            trend_rows = await repo.severity_by_day(since)

        severity_breakdown = _ordered_counter(summary["by_severity"], _SEVERITY_ORDER)
        severity_breakdown["unclassified"] = int(summary["unclassified"])

        return DashboardStats(
            runs={"total": summary["total_runs"], **dict(summary["by_status"])},
            assets={
                "total": summary["total_assets"],
                "with_issues": summary["assets_with_issues"],
            },
            findings={
                "total": summary["total_findings"],
                "severity_breakdown": severity_breakdown,
                "by_type": _ordered_counter(summary["by_type"], _FINDING_TYPE_ORDER),
                "unclassified": summary["unclassified"],
                # Marked false_positive; not in total or any breakdown (TASK-35).
                "dismissed": summary["dismissed"],
            },
            top_domains=[
                {"domain": domain, "count": count} for domain, count in top_domains
            ],
            top_evidence=top_evidence,
            agent_usage={
                "calls": agent_usage["calls"],
                "prompt_tokens": agent_usage["prompt_tokens"],
                "completion_tokens": agent_usage["completion_tokens"],
                "total_tokens": agent_usage["total_tokens"],
                "latency_ms": agent_usage["latency_ms"],
            },
            trends=build_trends(trend_rows, today),
        )