"""Dashboard aggregation service (TASK-11, v2.0).

Read-only composition over :class:`DashboardRepository`. The endpoint
``GET /api/stats`` and the ``/dashboard`` page share this one builder, so
there is exactly one definition of the dashboard model — like the CLI/Web UI
share the orchestrator. No writes happen anywhere in this module.
"""

from __future__ import annotations

from collections import Counter
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

    async def build(self) -> DashboardStats:
        async with self._session_factory() as session:
            repo = DashboardRepository(session)
            summary = await repo.summary()
            top_domains = await repo.top_domains(_DASHBOARD_TOP_LIMIT)
            top_evidence = await repo.top_evidence(_DASHBOARD_TOP_LIMIT)
            agent_usage = await repo.agent_usage()

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
        )