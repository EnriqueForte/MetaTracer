"""Durable scan-slot lock shared by processes that use the same database.

The in-memory semaphore still stops a second scan inside one process. This
module is what a second process sees: open ``pending``/``running`` rows,
serialized on the singleton ``concurrency_gate`` row.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import ScanAlreadyRunningError
from metatracer.db.models import ConcurrencyGate, Run, RunStatus

_OPEN = (RunStatus.pending, RunStatus.running)
GATE_ID = 1


async def reject_if_at_capacity(session: AsyncSession, limit: int) -> None:
    """Raise :class:`ScanAlreadyRunningError` when every durable slot is taken.

    Must run in the same transaction that inserts the new ``Run`` row.
    """
    await _lock_gate(session)
    ids = await list_open_run_ids(session)
    if len(ids) >= max(1, limit):
        raise ScanAlreadyRunningError(ids)


async def list_open_run_ids(session: AsyncSession) -> list[str]:
    result = await session.exec(select(Run.id).where(Run.status.in_(_OPEN)))
    return [str(run_id) for run_id in result.all()]


async def _lock_gate(session: AsyncSession) -> None:
    gate = await session.get(ConcurrencyGate, GATE_ID)
    if gate is None:
        session.add(ConcurrencyGate(id=GATE_ID))
        await session.flush()
    locked = select(ConcurrencyGate).where(ConcurrencyGate.id == GATE_ID).with_for_update()
    await session.exec(locked)
