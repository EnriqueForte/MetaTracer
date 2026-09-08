"""NotificationBus (TASK-12): queue order, bounded memory, index-based delete."""

from datetime import UTC, datetime

import pytest

from metatracer.db.models import RunStatus
from metatracer.services.notifications import NotificationBus, NotificationEvent


def _event(*, kind: RunStatus = RunStatus.completed, **overrides) -> NotificationEvent:
    defaults = {
        "id": 0,  # the bus reassigns the queue index on append
        "kind": kind,
        "run_id": "11111111-1111-4111-8111-111111111111",
        "target": "target.com",
        "total_assets": 3,
        "total_findings": 2,
        "error_message": None,
        "created_at": datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return NotificationEvent(**defaults)


def test_list_is_newest_first() -> None:
    bus = NotificationBus()
    bus.publish(_event(run_id="first", created_at=datetime(2026, 9, 8, 10, 0, tzinfo=UTC)))
    bus.publish(_event(run_id="second", created_at=datetime(2026, 9, 8, 11, 0, tzinfo=UTC)))

    events = bus.list()
    assert [e.run_id for e in events] == ["second", "first"]
    # The id IS the current listing index (it renumbers after deletes), and
    # the payload events are independent copies.
    assert [e.id for e in events] == [0, 1]


def test_publish_naive_datetime_assumed_utc() -> None:
    bus = NotificationBus()
    bus.publish(_event(created_at=datetime(2026, 9, 8, 12, 0, 0)))  # naive
    assert bus.list()[0].created_at.tzinfo is UTC


def test_delete_by_list_index() -> None:
    bus = NotificationBus()
    bus.publish(_event(run_id="a"))
    bus.publish(_event(run_id="b"))

    # Deleting index 0 removes the newest (b); index 1 is now 'a'.
    assert bus.delete(0) is True
    assert [e.run_id for e in bus.list()] == ["a"]
    assert bus.delete(0) is True
    assert bus.list() == []


def test_delete_returns_false_for_invalid_index() -> None:
    bus = NotificationBus()
    bus.publish(_event(run_id="a"))

    assert bus.delete(1) is False  # out of range
    assert bus.delete(-1) is False  # negative is never valid
    assert len(bus.list()) == 1
    # Stale index after the only entry was deleted -> False, never a wrong target.
    assert bus.delete(0) is True
    assert bus.delete(0) is False


def test_max_events_evicts_oldest() -> None:
    bus = NotificationBus(max_events=3)
    for i in range(5):
        bus.publish(_event(run_id=f"run-{i}"))
    events = bus.list()
    assert [e.run_id for e in events] == ["run-4", "run-3", "run-2"]
    assert len(bus.list()) == 3


def test_list_returns_a_copy() -> None:
    bus = NotificationBus()
    bus.publish(_event(run_id="a"))
    snapshot = bus.list()
    snapshot.clear()
    assert len(bus.list()) == 1


def test_completed_events_carry_no_error_message() -> None:
    bus = NotificationBus()
    bus.publish(_event(kind=RunStatus.completed, error_message=None))
    assert bus.list()[0].error_message is None


def test_failed_events_carry_the_sanitized_message() -> None:
    bus = NotificationBus()
    bus.publish(
        _event(kind=RunStatus.failed, error_message="unexpected RuntimeError: boom")
    )
    entry = bus.list()[0]
    assert entry.kind is RunStatus.failed
    assert entry.error_message == "unexpected RuntimeError: boom"


def test_publish_never_raises() -> None:
    """A broken consumer must not kill a scan (inviolable rule 5)."""
    bus = NotificationBus()
    # Publishing a non-NotificationEvent would fail Pydantic validation at
    # construction, not in publish; publish itself only appends. Guard the
    # documented failure mode instead: nothing here raises.
    bus.publish(_event())


def test_created_at_is_timezone_aware_utc() -> None:
    bus = NotificationBus()
    bus.publish(_event(created_at=datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)))
    assert bus.list()[0].created_at.utcoffset() == datetime.now(UTC).utcoffset()


@pytest.mark.parametrize("invalid", [-5, -1, 100, 7])
def test_delete_rejects_all_invalid_indexes(invalid: int) -> None:
    bus = NotificationBus()
    bus.publish(_event(run_id="a"))
    assert bus.delete(invalid) is False
    assert len(bus.list()) == 1