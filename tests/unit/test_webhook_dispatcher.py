"""Unit tests for TASK-15 webhooks: models, run_ref, repositories, dispatcher.

Covers the relay-buffer contract (idempotency, retry/backoff, fixed payload
keys, recover-pending on restart) with an in-memory SQLite engine and a fake
HTTP transport — no real network ever leaves the process.
"""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.api.webhooks import (
    PAYLOAD_KEYS,
    WebhookDispatcher,
)
from metatracer.db.engine import init_db
from metatracer.db.models import (
    Run,
    RunStatus,
    WebhookConfig,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from metatracer.db.repositories import (
    RunRepository,
    WebhookConfigRepository,
    WebhookDeliveryRepository,
)


@pytest.fixture()
async def engine(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/wh-unit.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_factory(engine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_run(sf) -> Run:
    async with sf() as session:
        return await RunRepository(session).create(
            Run(
                target_input='["t.com"]',
                allowed_scope='["t.com"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )


async def _seed_webhook(
    sf, *, event=RunStatus.completed, active=True, max_retries=3
) -> WebhookConfig:
    async with sf() as session:
        return await WebhookConfigRepository(session).create(
            WebhookConfig(
                name="alerts",
                url="https://hooks.example.com/wh",
                event=event,
                headers=json.dumps({"X-Token": "s3cr3t"}),
                max_retries=max_retries,
                active=active,
            )
        )


# --- run_ref ---------------------------------------------------------------

async def test_run_ref_is_generated_and_short(session_factory) -> None:
    run = await _seed_run(session_factory)
    assert run.run_ref is not None
    assert len(run.run_ref) == 10
    assert set(run.run_ref) <= set("23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ")


async def test_run_ref_is_unique(session_factory) -> None:
    runs = [await _seed_run(session_factory) for _ in range(5)]
    refs = {run.run_ref for run in runs}
    assert len(refs) == len(runs)


# --- repositories ----------------------------------------------------------

async def test_webhook_config_repo_crud(session_factory) -> None:
    async with session_factory() as session:
        repo = WebhookConfigRepository(session)
        cfg = await repo.create(
            WebhookConfig(name="a", url="https://x.example.com/h", event=RunStatus.completed)
        )
        fetched = await repo.get(cfg.id)
        assert fetched is not None and fetched.name == "a"
        fetched.active = False
        await repo.update(fetched)
        assert (await repo.get(cfg.id)).active is False
        assert await repo.delete(cfg.id) is True
        assert await repo.get(cfg.id) is None


async def test_list_active_by_event_filters(session_factory) -> None:
    await _seed_webhook(session_factory, event=RunStatus.completed)
    await _seed_webhook(session_factory, event=RunStatus.failed)
    await _seed_webhook(session_factory, event=RunStatus.completed, active=False)
    async with session_factory() as session:
        completed = await WebhookConfigRepository(session).list_active_by_event(RunStatus.completed)
        failed = await WebhookConfigRepository(session).list_active_by_event(RunStatus.failed)
        assert len(completed) == 1
        assert len(failed) == 1


async def test_delivery_unique_per_webhook_run(session_factory) -> None:
    run = await _seed_run(session_factory)
    cfg = await _seed_webhook(session_factory)
    async with session_factory() as session:
        repo = WebhookDeliveryRepository(session)
        first = await repo.create(
            WebhookDelivery(webhook_id=cfg.id, run_id=run.id, payload_json="{}")
        )
        second = await repo.get_by_webhook_run(cfg.id, run.id)
        assert second.id == first.id  # not a new row


async def test_list_pending_returns_only_due(session_factory) -> None:
    run = await _seed_run(session_factory)
    cfg = await _seed_webhook(session_factory)
    import time

    async with session_factory() as session:
        repo = WebhookDeliveryRepository(session)
        due = await repo.create(
            WebhookDelivery(webhook_id=cfg.id, run_id=run.id, payload_json="{}")
        )
        later = await repo.create(
            WebhookDelivery(
                webhook_id=cfg.id,
                run_id="other-run",
                payload_json="{}",
                next_retry_at=time.time() + 60,
            )
        )
        pending = await repo.list_pending()
        ids = {d.id for d in pending}
        assert due.id in ids
        assert later.id not in ids


# --- dispatcher (fake transport below) --------------------------------------

class _FakeTransport:
    """Stands in for WebhookDispatcher._send: returns (status_code, error).

    ``responses`` is a queue of outcomes: int status codes (HTTP path),
    ``"error"`` strings (network/5xx path) or ``Exception`` instances.
    """

    def __init__(self) -> None:
        # records (url, payload) per call + headers merged from the config
        self.calls: list[tuple[str, dict, dict]] = []
        self.responses: list[object] = []

    async def __call__(self, config: WebhookConfig, payload: dict):
        headers = json.loads(config.headers or "{}") or {}
        self.calls.append((config.url, payload, headers))
        if self.responses:
            resp = self.responses.pop(0)
        else:
            resp = 200
        if isinstance(resp, Exception):
            # emulate a network failure: _send returns an error string
            return None, "connection failed"
        if isinstance(resp, str):
            return None, resp
        return int(resp), None


def _dispatcher(sf, transport: _FakeTransport, **kw) -> WebhookDispatcher:
    d = WebhookDispatcher(sf, **kw)
    # JSON payload cache is the single source for body; the transport gets the
    # payload dict, so the fixed-keys guard is exercised through enqueue.
    d._send = transport  # type: ignore[assignment]
    return d


async def test_enqueue_terminal_persists_and_dispatches(session_factory) -> None:
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory)
    transport = _FakeTransport()
    dispatcher = _dispatcher(session_factory, transport)
    await dispatcher.enqueue_terminal(
        run.id,
        RunStatus.completed,
        target="t.com",
        total_assets=2,
        total_findings=3,
        executive_summary="ok",
    )
    # the send is scheduled as a background task: let it run
    await asyncio.sleep(0.05)
    assert len(transport.calls) == 1
    url, payload, headers = transport.calls[0]
    assert url == "https://hooks.example.com/wh"
    assert set(payload) == set(PAYLOAD_KEYS)
    assert payload["run_ref"] == run.run_ref
    assert payload["event"] == "completed"
    assert payload["total_findings"] == 3
    assert "X-Token" in headers

    async with session_factory() as session:
        rows = await WebhookDeliveryRepository(session).list_by_webhook(
            (await WebhookConfigRepository(session).list_all())[0].id
        )
        assert len(rows) == 1
        assert rows[0].status == WebhookDeliveryStatus.succeeded


async def test_enqueue_terminal_is_noop_for_non_terminal(session_factory) -> None:
    await _seed_run(session_factory)
    await _seed_webhook(session_factory)
    transport = _FakeTransport()
    dispatcher = _dispatcher(session_factory, transport)
    await dispatcher.enqueue_terminal("run-x", RunStatus.running)
    await asyncio.sleep(0.02)
    assert transport.calls == []
    async with session_factory() as session:
        rows = await WebhookDeliveryRepository(session).list_by_webhook(
            (await WebhookConfigRepository(session).list_all())[0].id
        )
        assert rows == []  # no delivery row for a non-terminal event


async def test_enqueue_terminal_skips_inactive_and_other_event(session_factory) -> None:
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory, event=RunStatus.failed)  # not completed
    await _seed_webhook(session_factory, event=RunStatus.completed, active=False)
    transport = _FakeTransport()
    await _dispatcher(session_factory, transport).enqueue_terminal(run.id, RunStatus.completed)
    await asyncio.sleep(0.02)
    assert transport.calls == []


async def test_enqueue_is_idempotent_per_run(session_factory) -> None:
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory)
    transport = _FakeTransport()
    dispatcher = _dispatcher(session_factory, transport)
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    # Let the first background attempt persist the delivery + send, then
    # re-enqueue: the relay-buffer row must be visible so no second send fires.
    await asyncio.sleep(0.1)
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    await asyncio.sleep(0.05)
    assert len(transport.calls) == 1  # second enqueue saw the existing row


async def test_http_4xx_is_rejected_not_retried(session_factory) -> None:
    run = await _seed_run(session_factory)
    cfg = await _seed_webhook(session_factory)
    transport = _FakeTransport()
    transport.responses = [400]
    dispatcher = _dispatcher(session_factory, transport)
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    await asyncio.sleep(0.05)
    async with session_factory() as session:
        row = await WebhookDeliveryRepository(session).get_by_webhook_run(cfg.id, run.id)
        assert row.status == WebhookDeliveryStatus.rejected
        assert row.status_code == 400
    assert len(transport.calls) == 1


async def test_http_error_retries_then_fails_at_cap(session_factory) -> None:
    run = await _seed_run(session_factory)
    cfg = await _seed_webhook(session_factory, max_retries=2)
    transport = _FakeTransport()
    transport.responses = ["boom", "boom"]
    dispatcher = _dispatcher(session_factory, transport, base_backoff=0.01, max_backoff=0.05)
    # First terminal event: attempt 1 fails, schedules a retry at now+0.01.
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    await asyncio.sleep(0.05)
    async with session_factory() as session:
        row = await WebhookDeliveryRepository(session).get_by_webhook_run(cfg.id, run.id)
        assert row.status == WebhookDeliveryStatus.pending  # still retriable
        assert row.attempts == 1
    # Second terminal event triggers the opportunistic sweep; attempt 2 fails
    # and reaches the cap -> terminal failed.
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    await asyncio.sleep(0.05)
    async with session_factory() as session:
        row = await WebhookDeliveryRepository(session).get_by_webhook_run(cfg.id, run.id)
        assert row.status == WebhookDeliveryStatus.failed
        assert row.attempts == 2
        assert row.last_error
    assert len(transport.calls) == 2


async def test_recover_pending_reenqueues_on_next_terminal(session_factory) -> None:
    run = await _seed_run(session_factory)
    cfg = await _seed_webhook(session_factory)
    # simulate a row left pending by a previous process (crash)
    async with session_factory() as session:
        await WebhookDeliveryRepository(session).create(
            WebhookDelivery(
                webhook_id=cfg.id,
                run_id=run.id,
                status=WebhookDeliveryStatus.pending,
                attempts=0,
                payload_json=json.dumps({"run_id": run.id, "event": "completed"}),
            )
        )
    transport = _FakeTransport()
    transport.responses = [200, 200]
    dispatcher = _dispatcher(session_factory, transport)
    # enqueue for a NEW run triggers recover_pending() first (it replays the
    # old pending row) and then dispatches the new run.
    run2 = await _seed_run(session_factory)
    await dispatcher.enqueue_terminal(run2.id, RunStatus.completed)
    # Poll until the recovered row reaches the terminal state (robust under
    # suite load, unlike a fixed sleep).
    for _ in range(50):
        await asyncio.sleep(0.02)
        async with session_factory() as session:
            recovered = await WebhookDeliveryRepository(session).get_by_webhook_run(
                cfg.id, run.id
            )
        if recovered is not None and recovered.status is not WebhookDeliveryStatus.pending:
            break
    async with session_factory() as session:
        recovered = await WebhookDeliveryRepository(session).get_by_webhook_run(cfg.id, run.id)
        assert recovered.status == WebhookDeliveryStatus.succeeded


async def test_payload_keys_never_leak_metadata(session_factory) -> None:
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory)
    transport = _FakeTransport()
    dispatcher = _dispatcher(session_factory, transport)
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed, executive_summary="a" * 1000)
    await asyncio.sleep(0.05)
    _, payload, _ = transport.calls[0]
    assert set(payload) <= set(PAYLOAD_KEYS)
    assert len(payload["executive_summary"]) <= 300
    assert "evidence" not in payload
    assert "headers" not in payload


async def test_watch_delta_counter_travels_in_payload(session_factory) -> None:
    """TASK-22 (v3.0, Eje A): ``new_findings`` is a fixed scalar payload key
    and defaults to 0 for non-watch runs (the contract stays flat and closed)."""
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory)
    transport = _FakeTransport()
    dispatcher = _dispatcher(session_factory, transport)
    # Non-watch run: key present, zero.
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed, target="t.com")
    await asyncio.sleep(0.05)
    _, payload, _ = transport.calls[0]
    assert payload["new_findings"] == 0
    assert set(payload) == set(PAYLOAD_KEYS)
    # Watch run (different run id -> new, non-duplicate delivery): the
    # count travels on the exact same key set.
    run2 = await _seed_run(session_factory)
    transport2 = _FakeTransport()
    dispatcher2 = _dispatcher(session_factory, transport2)
    await dispatcher2.enqueue_terminal(
        run2.id, RunStatus.completed, target="t.com", new_findings=3
    )
    await asyncio.sleep(0.05)
    _, payload2, _ = transport2.calls[0]
    assert payload2["new_findings"] == 3
    assert set(payload2) == set(PAYLOAD_KEYS)


async def test_send_rejects_loopback_target_even_with_https(session_factory) -> None:
    """Invariant rule 7 applies to egress: a webhook URL on loopback is refused.

    The real ``_send`` (not the fake transport) is exercised with a real
    ``NetworkSafetyGuard`` so the DNS/IP check runs before any socket opens.
    """
    from metatracer.core.safety.guard import NetworkSafetyGuard

    dispatcher = WebhookDispatcher(
        session_factory,
        guard=NetworkSafetyGuard(allow_loopback=False),
    )
    cfg = WebhookConfig(
        id="00000000-0000-4000-8000-000000000000",
        name="ssrf",
        url="https://127.0.0.1/intranet",
        event=RunStatus.completed,
    )
    status_code, error = await dispatcher._send(cfg, {"run_id": "r1"})
    assert status_code is None
    assert error is not None
    # the refusal reason must not leak the raw host in a way that exposes
    # internal addressing (sanitize_for_log keeps it readable; assert a
    # stable substring so the test does not depend on exact wording).
    assert "rejected" in error


async def test_shutdown_cancels_inflight_without_raising(session_factory) -> None:
    """shutdown() cancels in-flight send tasks and never raises.

    The relay buffer is already persisted, so an interrupted attempt is safe:
    the next recover_pending sweep retries from the database.
    """
    run = await _seed_run(session_factory)
    await _seed_webhook(session_factory)

    class _SlowTransport(_FakeTransport):
        async def __call__(self, config: WebhookConfig, payload: dict):
            await asyncio.sleep(5)
            return await super().__call__(config, payload)

    dispatcher = _dispatcher(session_factory, _SlowTransport())
    await dispatcher.enqueue_terminal(run.id, RunStatus.completed)
    # let the send task start and hit the sleep inside the transport
    await asyncio.sleep(0.05)
    assert len(dispatcher._tasks) == 1
    await dispatcher.shutdown()  # must cancel the sleep and not raise
    assert not dispatcher._tasks
    # the delivery row stays persisted (relay buffer semantics)
    async with session_factory() as session:
        cfg = (await WebhookConfigRepository(session).list_all())[0]
        row = await WebhookDeliveryRepository(session).get_by_webhook_run(cfg.id, run.id)
        assert row is not None and row.status == WebhookDeliveryStatus.pending