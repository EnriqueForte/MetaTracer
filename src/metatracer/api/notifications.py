"""GET/DELETE /api/notifications: in-memory run notifications (TASK-12, v2.0).

The bus lives on ``app.state.notifications_bus``: the orchestrator publishes
one event per terminal run (completed/failed) and this router exposes the
queue to the Web UI bell. Read-only GET; manual deletion by list index
(invalid indices answer 404 — there is no persisted id to validate against).
No business logic lives here; the bus owns the queue.
"""

from fastapi import APIRouter, HTTPException, Request, Response

from metatracer.api.schemas import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _bus(request: Request):
    """The one in-memory notification bus of this process (app wiring)."""
    return request.app.state.notifications_bus


@router.get("", response_model=NotificationListResponse)
async def list_notifications(request: Request) -> NotificationListResponse:
    """List the in-memory queue, newest first. Read-only: never writes."""
    events = _bus(request).list()
    return NotificationListResponse(
        total=len(events),
        notifications=[NotificationResponse.from_event(event) for event in events],
    )


@router.delete("/{index}", status_code=204)
async def delete_notification(index: int, request: Request) -> Response:
    """Delete one notification by list index (manual cleanup).

    404 when the index is out of range (or the entry was already deleted):
    events are ephemeral, so a stale index can never resolve to another event.
    """
    if not _bus(request).delete(index):
        raise HTTPException(status_code=404, detail="notification index out of range")
    return Response(status_code=204)