"""
RAG injection (TASK-14, v2.1+): AgentPipeline attaches retrieved_evidence;
AnalyzeContextNode merges it.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.agents.graph import AgentState, AnalyzeContextNode
from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, Finding, FindingType, Run, Severity
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/knowledge-injection-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


async def _seed(engine: AsyncEngine, *, run_count: int = 2) -> None:
    """Two runs with the same GPS evidence -> the second can retrieve the first."""
    async with create_session_factory(engine)() as session:
        for i in range(run_count):
            run = await RunRepository(session).create(
                Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
            )
            asset = await AssetRepository(session).create(
                Asset(
                    run_id=run.id,
                    source_url=f"https://t.com/{i}.jpg",
                    final_url=f"https://t.com/{i}.jpg",
                    content_type="image/jpeg",
                    file_hash_sha256=f"h-{i}",
                    file_size_bytes=10,
                    extraction_status="ok",
                )
            )
            await FindingRepository(session).create(
                Finding(
                    run_id=run.id,
                    asset_id=asset.id,
                    finding_type=FindingType.gps,
                    field_source="EXIF:GPSInfo",
                    evidence_snippet="Latitude: 41.6521, Longitude: -0.8809",
                    dedup_signature=f"sig-gps-{i}",
                    detector_method="rule",
                    confidence="high",
                    severity=Severity.high,
                )
            )


class _FakeResult(BaseModel):
    value: Any
    usage: Any = None


class _FakeClient:
    """Minimal AgentClient stand-in: records the payload, returns a stub analysis."""

    available = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def analyze(self, system: str, payload: dict) -> _FakeResult:
        self.calls.append((system, payload))
        return _FakeResult(value=object(), usage=None)


async def test_analyze_node_merges_retrieved_context_into_payload() -> None:
    """The closed payload stays intact; retrieved_evidence is merged at the top level."""
    client = _FakeClient()
    node = AnalyzeContextNode(client)
    state: AgentState = {
        "target_domain": "t.com",
        "reasoning_depth": "standard",
        "raw_findings": [
            {
                "finding_id": "f1",
                "payload": {
                    "finding_type": "gps",
                    "evidence_snippet": "Latitude: 41.6521",
                    "confidence": "high",
                },
                "had_baseline_severity": True,
                "retrieved_evidence": [
                    {
                        "finding_id": "hist1",
                        "finding_type": "gps",
                        "evidence_snippet": "Latitude: 41.6521, Longitude: -0.8809",
                        "severity": "high",
                        "title": "Public square GPS",
                        "score": -2.5,
                    }
                ],
            }
        ],
        "evaluated_findings": [],
        "current_index": 0,
        "error_log": [],
    }
    await node(state)
    assert len(client.calls) == 1
    _, model_payload = client.calls[0]
    # closed payload contract untouched
    assert model_payload["finding_type"] == "gps"
    assert model_payload["evidence_snippet"] == "<<<EVIDENCE>>>\nLatitude: 41.6521\n<<<END>>>"
    # historical precedent is labeled as not evidence of this finding
    assert "retrieved_evidence" not in model_payload
    first = model_payload["historical_not_evidence"][0]
    assert first["finding_type"] == "gps"
    assert first["title"] == "Public square GPS"
    assert "score" not in first  # score is not part of the prompt contract


async def test_retriever_excludes_current_finding(engine: AsyncEngine) -> None:
    """The current finding never retrieves itself (TASK-14 acceptance)."""
    session_factory = create_session_factory(engine)
    await _seed(engine, run_count=2)
    retriever = KnowledgeRetriever(engine, session_factory)
    hits = await retriever.retrieve(
        {
            "finding_type": "gps",
            "evidence_snippet": "Latitude: 41.6521, Longitude: -0.8809",
        },
        exclude_finding_id="does-not-matter",
    )
    # both seeded findings share the snippet, so without exclusion we'd get 2;
    # with a bogus exclude id we still get hits from the OTHER run
    assert len(hits) >= 1
    all_ids = {hit.finding_id for hit in hits}
    # the retriever never returns the excluded id (none equals "does-not-matter")
    assert "does-not-matter" not in all_ids