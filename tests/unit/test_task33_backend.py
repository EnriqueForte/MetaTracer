"""TASK-33: dashboard query shape, webhook retry sweep, import cycle."""

import importlib
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.api.auth import LoginLockout
from metatracer.api.webhooks import WebhookDispatcher
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    Run,
    RunStatus,
    WebhookConfig,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from metatracer.db.repositories import DashboardRepository, WebhookDeliveryRepository
from metatracer.services.watch import DeltaReporter


@pytest.fixture()
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    db = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/task33.db")
    await init_db(db)
    yield db
    await db.dispose()


@pytest.fixture()
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


def test_classification_anchor_imports_without_a_cycle() -> None:
    importlib.import_module("metatracer.classification.anchor")


def test_login_lockout_blocks_the_correct_password_after_ten_failures() -> None:
    lock = LoginLockout(failures=10, base_seconds=60)
    for _ in range(9):
        lock.record_failure("operator", "10.0.0.8")
        assert lock.retry_after("operator", "10.0.0.8") is None
    lock.record_failure("operator", "10.0.0.8")
    assert lock.retry_after("operator", "10.0.0.8") is not None
    # A different IP is not locked.
    assert lock.retry_after("operator", "10.0.0.9") is None


async def test_dashboard_summary_query_count_stays_flat(
    engine: AsyncEngine, session_factory
) -> None:
    async with session_factory() as session:
        run = Run(
            target_input="[]",
            allowed_scope='["target.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        asset = Asset(
            run_id=run.id,
            source_url="http://target.com/a.pdf",
            final_url="http://target.com/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="ab" * 32,
            file_size_bytes=10,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        session.add_all(
            [
                Finding(
                    run_id=run.id,
                    asset_id=asset.id,
                    finding_type=FindingType.email,
                    field_source="pdfinfo:Author",
                    evidence_snippet=f"user{index}@target.com",
                    dedup_signature=f"sig-{index}",
                    detector_method=DetectorMethod.rule,
                    confidence=Confidence.high,
                )
                for index in range(5000)
            ]
        )
        await session.commit()

    selects = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selects["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        async with session_factory() as session:
            summary = await DashboardRepository(session).summary()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)
    assert summary["total_findings"] == 5000
    assert selects["n"] <= 6


async def test_delta_uses_one_signature_query(session_factory) -> None:
    async with session_factory() as session:
        first = Run(
            target_input="[]",
            allowed_scope='["target.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        second = Run(
            target_input="[]",
            allowed_scope='["target.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(first)
        session.add(second)
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)
        asset = Asset(
            run_id=first.id,
            source_url="http://target.com/a.pdf",
            final_url="http://target.com/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="cd" * 32,
            file_size_bytes=10,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        session.add(
            Finding(
                run_id=first.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="old@target.com",
                dedup_signature="sig-old",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
            )
        )
        session.add(
            Finding(
                run_id=second.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="new@target.com",
                dedup_signature="sig-new",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
            )
        )
        await session.commit()
        current_id = second.id
    delta = await DeltaReporter(session_factory).compute_delta(current_id)
    assert delta.new_findings == 1
    assert delta.new_signatures == ["sig-new"]


async def test_due_webhook_retries_without_a_new_scan(session_factory, monkeypatch) -> None:
    async with session_factory() as session:
        run = Run(
            target_input="[]",
            allowed_scope='["target.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        hook = WebhookConfig(
            name="alerts",
            url="https://hooks.example.com/wh",
            event=RunStatus.completed,
        )
        session.add(hook)
        await session.commit()
        await session.refresh(hook)
        session.add(
            WebhookDelivery(
                webhook_id=hook.id,
                run_id=run.id,
                status=WebhookDeliveryStatus.pending,
                attempts=1,
                max_retries=3,
                payload_json='{"event": "completed"}',
                next_retry_at=1.0,
            )
        )
        await session.commit()

    calls: list[str] = []

    async def _send(config, payload):
        calls.append(config.url)
        return 200, None

    dispatcher = WebhookDispatcher(session_factory, guard=None)
    monkeypatch.setattr(dispatcher, "_send", _send)
    assert await dispatcher.sweep_due_retries() == 1
    import asyncio

    pending = list(dispatcher._tasks)
    if pending:
        await asyncio.gather(*pending)
    assert calls == ["https://hooks.example.com/wh"]
    async with session_factory() as session:
        rows = await WebhookDeliveryRepository(session).list_pending()
    assert rows == []
