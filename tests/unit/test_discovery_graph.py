"""Discovery edges persist independently of the run; the graph endpoint caps them."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    CorrelationKind,
    DetectorMethod,
    DiscoveryEdge,
    DiscoveryEdgeKind,
    ExtractionStatus,
    Finding,
    FindingType,
    GraphNodeKind,
    RawMetadataItem,
    Run,
    RunStatus,
)
from metatracer.db.repositories import DiscoveryEdgeRepository
from metatracer.detectors.consolidator import dedup_signature
from metatracer.detectors.correlate import collect_observations
from metatracer.services.correlation import record_observations
from metatracer.services.graph import MAX_GRAPH_EDGES, MAX_GRAPH_NODES, RunGraphService


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/graph.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _run(session: AsyncSession) -> Run:
    run = Run(
        target_input='["https://acme.test/"]',
        allowed_scope='["acme.test"]',
        scope_confirmed=True,
        status=RunStatus.running,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_duplicate_edges_are_ignored(session_factory) -> None:
    async with session_factory() as session:
        run = await _run(session)
        repo = DiscoveryEdgeRepository(session)
        first = await repo.add(
            run.id,
            "https://acme.test/",
            "https://acme.test/a.pdf",
            DiscoveryEdgeKind.document,
        )
        again = await repo.add(
            run.id,
            "https://acme.test/",
            "https://acme.test/a.pdf",
            DiscoveryEdgeKind.document,
        )
        assert first is not None and again is not None
        assert first.id == again.id
        listed = await repo.list_by_run(run.id)
        assert len(listed) == 1


async def test_graph_joins_assets_and_counts_metrics(session_factory) -> None:
    async with session_factory() as session:
        run = await _run(session)
        asset = Asset(
            run_id=run.id,
            source_url="https://acme.test/a.pdf",
            final_url="https://acme.test/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="aa" * 32,
            file_size_bytes=12,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        await DiscoveryEdgeRepository(session).add(
            run.id,
            "https://acme.test/",
            "https://acme.test/a.pdf",
            DiscoveryEdgeKind.document,
        )
        session.add(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="ada@acme.test",
                dedup_signature=dedup_signature(asset.id, FindingType.email, "ada@acme.test"),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
            )
        )
        await session.commit()
        run_id = run.id
        asset_id = asset.id

    graph = await RunGraphService(session_factory).get(run_id)
    assert graph.crawl.truncated is False
    kinds = {node.kind for node in graph.crawl.nodes}
    assert GraphNodeKind.page in kinds
    assert GraphNodeKind.asset in kinds
    asset_node = next(node for node in graph.crawl.nodes if node.kind is GraphNodeKind.asset)
    assert asset_node.asset_id == asset_id
    assert graph.metrics.by_content_type["application/pdf"] == 1
    assert graph.metrics.by_finding_type["email"] == 1
    assert graph.metrics.by_extraction_status["ok"] == 1


async def test_correlation_layer_is_bipartite_not_identity(session_factory) -> None:
    async with session_factory() as session:
        run = await _run(session)
        assets: list[Asset] = []
        for name, digest in (("one.jpg", "bb"), ("two.jpg", "cc")):
            asset = Asset(
                run_id=run.id,
                source_url=f"https://acme.test/{name}",
                final_url=f"https://acme.test/{name}",
                content_type="image/jpeg",
                file_hash_sha256=digest * 32,
                file_size_bytes=8,
                extraction_status=ExtractionStatus.ok,
            )
            session.add(asset)
            assets.append(asset)
        await session.commit()
        for asset in assets:
            await session.refresh(asset)
            item = RawMetadataItem(
                asset_id=asset.id,
                namespace="exif",
                key="BodySerialNumber",
                value="SN-88421",
            )
            observations = collect_observations([item], [])
            await record_observations(session, run.id, asset.id, observations)
        run_id = run.id

    graph = await RunGraphService(session_factory).get(run_id)
    assert graph.correlations.notice is not None
    assert "not proof of common identity" in graph.correlations.notice.lower()
    value_nodes = [node for node in graph.correlations.nodes if node.kind is GraphNodeKind.value]
    assert len(value_nodes) == 1
    assert value_nodes[0].correlation_kind is CorrelationKind.device_serial
    assert len(graph.correlations.edges) == 2


async def test_correlation_layer_keeps_only_this_run_assets(session_factory) -> None:
    """A shared value may exist in other runs; the scan graph stays on this run."""
    async with session_factory() as session:
        first = await _run(session)
        second = await _run(session)
        assets: list[tuple[str, Asset]] = []
        for run, name, digest in (
            (first, "one.jpg", "11"),
            (first, "two.jpg", "22"),
            (second, "other.jpg", "33"),
        ):
            asset = Asset(
                run_id=run.id,
                source_url=f"https://acme.test/{name}",
                final_url=f"https://acme.test/{name}",
                content_type="image/jpeg",
                file_hash_sha256=digest * 32,
                file_size_bytes=8,
                extraction_status=ExtractionStatus.ok,
            )
            session.add(asset)
            assets.append((run.id, asset))
        await session.commit()
        for run_id, asset in assets:
            await session.refresh(asset)
            item = RawMetadataItem(
                asset_id=asset.id,
                namespace="exif",
                key="BodySerialNumber",
                value="SN-88421",
            )
            await record_observations(session, run_id, asset.id, collect_observations([item], []))
        first_id = first.id

    graph = await RunGraphService(session_factory).get(first_id)
    asset_nodes = [node for node in graph.correlations.nodes if node.kind is GraphNodeKind.asset]
    assert {node.label for node in asset_nodes} == {"one.jpg", "two.jpg"}
    assert len(graph.correlations.edges) == 2


async def test_graph_truncates_at_the_render_cap(session_factory) -> None:
    async with session_factory() as session:
        run = await _run(session)
        for index in range(MAX_GRAPH_EDGES + 1):
            session.add(
                DiscoveryEdge(
                    run_id=run.id,
                    from_url="https://acme.test/",
                    to_url=f"https://acme.test/doc-{index}.pdf",
                    kind=DiscoveryEdgeKind.document,
                )
            )
        await session.commit()
        run_id = run.id

    graph = await RunGraphService(session_factory).get(run_id)
    assert graph.crawl.truncated is True
    assert len(graph.crawl.edges) <= MAX_GRAPH_EDGES
    assert len(graph.crawl.nodes) <= MAX_GRAPH_NODES
