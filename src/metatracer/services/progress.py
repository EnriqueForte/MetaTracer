"""ProgressBus: in-memory pub/sub with per-run history for SSE replay (TASK-06, 6.3).

The orchestrator invokes :meth:`ProgressBus.publish` synchronously from the
event-loop thread (it is the ``on_progress`` callback of the scan). The SSE
endpoint subscribes per run: the new queue is pre-loaded with the run's full
event history BEFORE it is registered, so a client that connects late — or
reconnects — receives every event from the start, and a client connecting
after the terminal event gets the complete history and closes immediately.

Both ``publish`` and ``subscribe`` are synchronous and never suspend between
replaying history and registering the queue, so no event can be lost between
the two (single event loop, cooperative scheduling).

Memory is bounded by ``max_runs``: the oldest runs' history is evicted. With a
single active scan per process the running run is always the most recent one,
so eviction never truncates an in-flight stream.
"""

import asyncio
import logging

from metatracer.services.orchestrator import ProgressEvent, ProgressStage

logger = logging.getLogger("metatracer.services.progress")

TERMINAL_STAGES = (ProgressStage.completed, ProgressStage.failed, ProgressStage.aborted)


class ProgressBus:
    """Fan-out of orchestrator ProgressEvents to per-run subscriber queues."""

    def __init__(self, max_runs: int = 100) -> None:
        self._max_runs = max_runs
        self._history: dict[str, list[ProgressEvent]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[ProgressEvent]]] = {}

    def publish(self, event: ProgressEvent) -> None:
        """Record one event and dispatch it to the run's current subscribers."""
        history = self._history.setdefault(event.run_id, [])
        history.append(event)
        if len(self._history) > self._max_runs:
            self._evict_oldest(except_run_id=event.run_id)
        for queue in self._subscribers.get(event.run_id, ()):
            queue.put_nowait(event)

    def subscribe(self, run_id: str) -> asyncio.Queue[ProgressEvent]:
        """Return a queue pre-loaded with the run's history (replay).

        When the run already reached a terminal stage the queue is NOT
        registered for future dispatch: the replayed history ends with the
        terminal event and the consumer closes after it.
        """
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        history = self._history.get(run_id, [])
        for event in history:
            queue.put_nowait(event)
        if not history or history[-1].stage not in TERMINAL_STAGES:
            self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def has_history(self, run_id: str) -> bool:
        """True when this process still holds replay events for the run."""
        return bool(self._history.get(run_id))

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        """Drop a subscriber queue (client disconnected or stream finished)."""
        subscribers = self._subscribers.get(run_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[run_id]

    def _evict_oldest(self, *, except_run_id: str) -> None:
        """Drop the oldest run's history; never the run currently publishing."""
        for key in self._history:
            if key != except_run_id:
                self._history.pop(key)
                self._subscribers.pop(key, None)
                logger.debug("evicted progress history of run %s", key)
                return
