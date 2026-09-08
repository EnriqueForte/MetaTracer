"""NotificationBus: in-memory queue of run-terminal notifications (TASK-12, v2.0).

The orchestrator emits one event per terminal run (``completed`` / ``failed``)
through this bus; the Web UI bell polls ``GET /api/notifications`` and the
operator deletes entries manually by list index. Design invariants:

- **Cero dependencias nuevas**: no Redis, no worker, no table. The queue lives
  in process memory only, so it empties on restart — that is the contract, not
  a limitation (see ``.aicontext/tasks/12-notifications.md``).
- **Cero acoplamiento**: the bus is injected into the orchestrator exactly like
  ``on_progress``; the pipeline never knows it exists.
- **Cero enums nuevos**: ``kind`` reuses ``run.status`` and the severity of the
  bell badge is a presentation detail, not a data contract.
- **Solo texto y contadores**: events carry target, counters and a sanitized
  error message — never snippets, bytes or secrets.
- Memory is bounded by ``max_events``: the oldest event is dropped. ``list()``
  returns a copy and ``delete()`` works on the *listing index* (newest first),
  so reuse of a stale index after a delete is a 404, never a wrong target.

``publish`` is synchronous (same event-loop thread as the orchestrator, like
``ProgressBus.publish``) and never raises: a broken consumer must not kill a
scan (inviolable rule 5).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from metatracer.db.models import RunStatus

DEFAULT_MAX_EVENTS = 100


class NotificationEvent(BaseModel):
    """One terminal-run notification; fields mirror the persisted Run counters.

    ``kind`` is a ``run.status`` value (``completed`` | ``failed``),
    ``error_message`` is the sanitized orchestrator message (always ``None``
    for ``completed``), and ``created_at`` is timezone-aware UTC.
    """

    id: int  # queue index (0-based, stable within the process)
    kind: RunStatus
    run_id: str
    target: str
    total_assets: int
    total_findings: int
    error_message: str | None = None
    created_at: datetime


class NotificationBus:
    """Append-only FIFO of notification events with bounded memory."""

    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self._max_events = max_events
        self._events: list[NotificationEvent] = []

    def publish(self, event: NotificationEvent) -> None:
        """Append one event, dropping the oldest when the queue is full.

        Defensive normalization: a naive ``created_at`` is assumed to be UTC
        (SQLite returns naive datetimes on read; every write is UTC). The
        listing index is assigned by :meth:`list`, not here.
        """
        if event.created_at.tzinfo is None:
            event.created_at = event.created_at.replace(tzinfo=UTC)
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events.pop(0)

    def list(self) -> list[NotificationEvent]:
        """Newest first, as copies with ``id`` = the current listing index.

        The id is deliberately **not** stable (contract: "no notification.id
        estable"): deleting entry N renumbers the rest, and a stale index can
        never resolve to a wrong target — the API answers 404 out of range.
        Copies are returned so callers can never mutate the queue.
        """
        events = [event.model_copy() for event in reversed(self._events)]
        for index, event in enumerate(events):
            event.id = index
        return events

    def delete(self, list_index: int) -> bool:
        """Remove the event at a *listing* index; False when out of range.

        The caller (API router) maps False to 404: without persisted ids there
        is no stable identity to validate against.
        """
        if list_index < 0 or list_index >= len(self._events):
            return False
        del self._events[-(list_index + 1)]
        return True