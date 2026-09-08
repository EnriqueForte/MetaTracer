"""GET /api/stats: aggregated dashboard data (TASK-11, v2.0).

Read-only endpoint. It delegates to the shared DashboardStatsService — the
same one nothing else calls yet, but the /dashboard page will. Always 200:
an empty local database is a valid dashboard (everything zero).
"""

from fastapi import APIRouter, Request

from metatracer.api.schemas import DashboardStatsResponse
from metatracer.services.dashboard import DashboardStatsService

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=DashboardStatsResponse)
async def get_stats(request: Request) -> DashboardStatsResponse:
    """One aggregated snapshot of runs, findings, top domains and agent usage."""
    service = DashboardStatsService(request.app.state.session_factory)
    stats = await service.build()
    return DashboardStatsResponse.from_dashboard_stats(stats)