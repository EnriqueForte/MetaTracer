"""ProgressBus unit tests (TASK-06, subtask 6.3): replay, fan-out, eviction.

The bus is the SSE backbone: any regression here breaks the live scan progress
in the Web UI and the API streaming endpoint. These tests exercise the real
queue semantics without any HTTP layer.
"""

import asyncio

import pytest

from metatracer.services.orchestrator import ProgressEvent, ProgressStage
from metatracer.services.progress import ProgressBus

RUN = "2c3ab48a-4c69-4f2e-8bf3-6f7d83d2f1a0"


def _event(stage: ProgressStage, seq: int = 0) -> ProgressEvent:
    return ProgressEvent(
        run_id=RUN,
        stage=stage,
        current_step=seq,
        total_steps=3,
        message=f"step {seq}",
    )


async def test_new_subscriber_receives_full_history() -> None:
    bus = ProgressBus()
    bus.publish(_event(ProgressStage.extraction, 1))
    bus.publish(_event(ProgressStage.detection, 2))
    queue = bus.subscribe(RUN)
    replayed: list[ProgressEvent] = []
    while not queue.empty():
        replayed.append(queue.get_nowait())
    assert [e.current_step for e in replayed] == [1, 2]


async def test_terminal_run_is_not_registered_for_future_dispatch() -> None:
    bus = ProgressBus()
    bus.publish(_event(ProgressStage.extraction, 1))
    bus.publish(_event(ProgressStage.completed, 2))
    queue = bus.subscribe(RUN)
    # After the terminal event the queue is closed to new events: publishing
    # more must never reach a subscriber that joined after completion.
    bus.publish(_event(ProgressStage.detection, 3))
    assert queue.empty() is False  # replay 1, 2
    replayed: list[ProgressEvent] = []
    while not queue.empty():
        replayed.append(queue.get_nowait())
    assert [e.current_step for e in replayed] == [1, 2]


async def test_subscriber_gets_live_events_after_replay() -> None:
    bus = ProgressBus()
    bus.publish(_event(ProgressStage.extraction, 1))
    queue = bus.subscribe(RUN)
    bus.publish(_event(ProgressStage.detection, 2))
    received: list[ProgressEvent] = []
    for _ in range(2):
        received.append(await asyncio.wait_for(queue.get(), timeout=1))
    assert [e.current_step for e in received] == [1, 2]


async def test_unsubscribe_removes_only_that_queue() -> None:
    bus = ProgressBus()
    queue_a = bus.subscribe(RUN)
    queue_b = bus.subscribe(RUN)
    bus.publish(_event(ProgressStage.extraction, 1))
    bus.unsubscribe(RUN, queue_a)
    # queue_b must still be registered: a publish must not raise and must reach it.
    bus.publish(_event(ProgressStage.detection, 2))
    first = await asyncio.wait_for(queue_b.get(), timeout=1)
    assert first.current_step == 1
    # queue_a was unregistered BEFORE the second publish, so it must only have
    # the replayed event; drain it, then a new publish must never reach it.
    await asyncio.wait_for(queue_a.get(), timeout=1)
    bus.publish(_event(ProgressStage.detection, 3))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue_a.get(), timeout=0.1)


async def test_eviction_drops_oldest_run_history_only() -> None:
    bus = ProgressBus(max_runs=2)
    bus.publish(_event(ProgressStage.extraction, 1))  # run A
    bus.publish(
        ProgressEvent(
            run_id="run-b",
            stage=ProgressStage.extraction,
            current_step=1,
            total_steps=3,
            message="b",
        )
    )
    bus.publish(
        ProgressEvent(
            run_id="run-c",
            stage=ProgressStage.extraction,
            current_step=1,
            total_steps=3,
            message="c",
        )
    )
    # run A was evicted; run-b and run-c both survive.
    assert bus._history.get("run-a") is None
    assert set(bus._history) == {"run-b", "run-c"}


async def test_eviction_never_drops_the_run_currently_publishing() -> None:
    bus = ProgressBus(max_runs=1)
    bus.publish(_event(ProgressStage.extraction, 1))  # fills the single slot
    # Publishing AGAIN to the same run must not evict it (in-flight stream safe).
    bus.publish(_event(ProgressStage.detection, 2))
    assert RUN in bus._history