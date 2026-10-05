"""Read-only comparison of two runs (TASK-35, block 35.4).

Same identity as the watch delta (:func:`finding_identity`): asset final URL,
finding type and normalized snippet. ``a`` is the baseline and ``b`` the run
being reviewed:

- ``new``: in ``b`` and not in ``a``;
- ``resolved``: in ``a`` and not in ``b``;
- ``persistent``: in both (reported with ``b``'s row).

No writes, no network, no LLM. Evidence travels unchanged (rule 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import RunNotFoundError
from metatracer.db.models import Finding, Run
from metatracer.db.repositories import FindingRepository, RunRepository
from metatracer.detectors.consolidator import finding_identity


@dataclass(slots=True)
class ComparedFinding:
    finding: Finding
    asset_url: str
    identity: str


@dataclass(slots=True)
class RunComparison:
    a: Run
    b: Run
    new: list[ComparedFinding] = field(default_factory=list)
    resolved: list[ComparedFinding] = field(default_factory=list)
    persistent: list[ComparedFinding] = field(default_factory=list)


def _index(rows: list[tuple[Finding, str]]) -> dict[str, ComparedFinding]:
    indexed: dict[str, ComparedFinding] = {}
    for finding, url in rows:
        identity = finding_identity(url, finding.finding_type, finding.evidence_snippet)
        indexed.setdefault(identity, ComparedFinding(finding, url, identity))
    return indexed


async def compare_runs(
    session_factory: async_sessionmaker[AsyncSession], a_id: str, b_id: str
) -> RunComparison:
    async with session_factory() as session:
        runs = RunRepository(session)
        a = await runs.get(a_id)
        b = await runs.get(b_id)
        if a is None or b is None:
            raise RunNotFoundError("run not found")
        repo = FindingRepository(session)
        left = _index(await repo.with_asset_url([a_id]))
        right = _index(await repo.with_asset_url([b_id]))
    result = RunComparison(a=a, b=b)
    for identity, item in right.items():
        (result.persistent if identity in left else result.new).append(item)
    result.resolved = [item for identity, item in left.items() if identity not in right]
    return result
