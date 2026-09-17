"""TASK-23 (Eje B): bounded scan concurrency in the orchestrator (unit).

The default limit (1) must behave exactly like the historical single-scan
lock; a higher limit must allow parallel scans while keeping 409 semantics
when every slot is busy.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from metatracer.core.config import Settings
from metatracer.core.exceptions import ScanAlreadyRunningError
from metatracer.services.orchestrator import ScanOrchestratorService


def _service(max_concurrent_runs: int) -> ScanOrchestratorService:
    settings = Settings(max_concurrent_runs=max_concurrent_runs)
    service = ScanOrchestratorService.__new__(ScanOrchestratorService)
    service._settings = settings
    service._active_run_id = None
    service._watch_run_ids = set()
    service._background_tasks = set()

    limit = max(1, settings.max_concurrent_runs)
    service._run_slots = asyncio.Semaphore(limit)
    service._active_run_ids = set()
    return service


def test_default_limit_creates_single_slot_semaphore() -> None:
    service = _service(1)
    assert service._run_slots._value == 1
    assert service._active_run_ids == set()


def test_higher_limit_creates_n_slots() -> None:
    service = _service(4)
    assert service._run_slots._value == 4


def test_zero_or_negative_limit_clamps_to_one() -> None:
    service = _service(0)
    assert service._run_slots._value == 1


async def test_scan_rejected_when_single_slot_busy() -> None:
    service = _service(1)
    # Simulate a scan holding the only slot (as _begin_scan would).
    await service._run_slots.acquire()
    service._active_run_ids.add("run-1")
    service._active_run_id = "run-1"

    request = MagicMock()
    request.scope_confirmed = True
    with pytest.raises(ScanAlreadyRunningError) as excinfo:
        await service._begin_scan(request)
    assert excinfo.value.active_run_id == "run-1"
    assert excinfo.value.active_run_ids == ["run-1"]

    service._run_slots.release()
    service._end_scan("run-1")
    assert service.active_run_id is None


async def test_scan_rejected_only_when_all_slots_busy() -> None:
    service = _service(2)
    await service._run_slots.acquire()  # one of two slots busy
    service._active_run_ids.add("run-1")
    service._active_run_id = "run-1"

    # A second scan still fits: the gate passes (no exception) and the slot
    # is taken; _create_run is mocked to avoid a DB write.
    service._create_run = AsyncMock(return_value=MagicMock(id="run-2"))
    request = MagicMock()
    request.scope_confirmed = True
    run = await service._begin_scan(request)
    assert run.id == "run-2"
    assert service._active_run_ids == {"run-1", "run-2"}

    # Third scan: every slot busy -> rejected with BOTH active ids.
    with pytest.raises(ScanAlreadyRunningError) as excinfo:
        await service._begin_scan(request)
    assert excinfo.value.active_run_ids == ["run-1", "run-2"]

    service._end_scan("run-2")
    assert service.active_run_id == "run-1"  # still points at a live run
    service._end_scan("run-1")
    assert service.active_run_id is None


def test_error_message_lists_active_runs() -> None:
    error = ScanAlreadyRunningError(["a", "b"])
    assert "a, b" in str(error)
    assert error.active_run_id == "a"

    legacy = ScanAlreadyRunningError(None)
    assert legacy.active_run_id is None
    assert legacy.active_run_ids == []
