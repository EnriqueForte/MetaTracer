"""Webhook configuration CRUD + outbound delivery dispatcher (TASK-15, v2.2).

Design contract:

- Outbound only, consumed by third-party endpoints (Slack/Discord/Teams webhook
  URLs, custom listeners). The URL must be HTTPS and is validated at write
  time.
- The payload is a **flat JSON document built from the persisted run row and
  its counters** — never file bytes, never raw metadata values, never the
  executive summary beyond a sanitized character cap. The exact set of keys is
  fixed in this module (single source of truth); no arbitrary template.
- Delivery is idempotent per ``(webhook_id, run_id)``: :class:`WebhookDelivery`
  rows are the relay buffer, survive restarts, and retries re-send the exact
  cached payload with exponential backoff up to ``max_retries``.
- A broken or unreachable webhook never fails the scan (inviolable rule 5):
  the orchestrator calls :meth:`WebhookDispatcher.enqueue_terminal` in a
  ``try/except`` and the HTTP send happens with ``asyncio.create_task`` so the
  pipeline does not wait on remote endpoints.
- Outbound HTTP uses a dedicated locked-down client (HTTPS-only, no
  redirects, short timeouts, body never read). Webhook URLs are operator
  egress to third-party channels — not in-scope assets — so they must NOT go
  through the run's ``safe_httpx_request`` gateway (which enforces the run
  scope and would reject them); the client is used instead, with the write
  time HTTPS validation re-checked at send time.
- Secrets: the plaintext HMAC secret is accepted at the CLI/API edge and
  stored on the config (same treatment as ``headers``, which already hold
  tokens). It is never returned by a read API. Deliveries with a secret send
  ``X-MetaTracer-Timestamp`` and ``X-MetaTracer-Signature`` over the exact
  body bytes. A pre-TASK-27 row that only has ``signature_secret_hash`` is
  delivered unsigned, with a warning, until the operator sets the secret again.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from metatracer.core.exceptions import SecurityViolationError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import RunStatus, WebhookConfig, WebhookDelivery, WebhookDeliveryStatus
from metatracer.db.repositories import (
    WebhookConfigRepository,
    WebhookDeliveryRepository,
)

logger = logging.getLogger("metatracer.api.webhooks")


# Fixed payload keys (single source of truth). Keys are lowercase, per the
# data-contract convention; values are all scalar (str | int | None).
PAYLOAD_KEYS = (
    "run_id",
    "run_ref",
    "event",
    "target",
    "total_assets",
    "total_findings",
    # TASK-22 / TASK-50: watch delta counters. Scalar like the rest; 0 when
    # the run produced no deltas or was not a watch iteration. Never arrays.
    "new_findings",
    "resolved_findings",
    "severity_up_count",
    "executive_summary",
    "error_message",
)


class WebhookCreate(BaseModel):
    """POST /api/webhooks body. URL is HTTPS-only; everything else optional."""

    url: HttpUrl
    name: str | None = Field(default=None, max_length=80)
    event: RunStatus = RunStatus.completed
    headers: dict[str, str] = Field(default_factory=dict)
    max_retries: int = Field(default=3, ge=0, le=10)
    active: bool = True
    signature_secret: str | None = Field(default=None, max_length=256)

    @field_validator("url")
    @classmethod
    def _https_only(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("webhook URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def _terminal_event(self) -> WebhookCreate:
        if self.event not in (RunStatus.completed, RunStatus.failed, RunStatus.aborted):
            raise ValueError("event must be a terminal status (completed|failed|aborted)")
        return self


class WebhookUpdate(BaseModel):
    """PUT /api/webhooks/{id} body. All fields optional; unchanged when absent."""

    url: HttpUrl | None = None
    name: str | None = Field(default=None, max_length=80)
    event: RunStatus | None = None
    headers: dict[str, str] | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    active: bool | None = None
    signature_secret: str | None = Field(default=None, max_length=256)

    @field_validator("url")
    @classmethod
    def _https_only(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("webhook URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def _terminal_event(self) -> WebhookUpdate:
        if self.event is not None and self.event not in (
            RunStatus.completed,
            RunStatus.failed,
            RunStatus.aborted,
        ):
            raise ValueError("event must be a terminal status (completed|failed|aborted)")
        return self


def _hash_secret(secret: str) -> str:
    """SHA-256 of the plaintext secret. Marks legacy rows; not used to sign."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _apply_signature_secret(config: WebhookConfig, secret: str | None) -> None:
    """Persist a new plaintext secret. Empty values leave the stored secret as-is."""
    if not secret:
        return
    config.signature_secret = secret
    config.signature_secret_hash = _hash_secret(secret)


def webhook_body_bytes(payload: dict[str, Any]) -> bytes:
    """Canonical body: UTF-8 JSON, compact separators, sorted keys.

    This exact byte string is what is signed and what is sent (``content=``).
    Receivers must HMAC the raw body, not a re-encoded document.
    """
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _signature_status(config: WebhookConfig) -> str:
    """``active`` | ``needs_secret`` | ``none``. Never reveals the secret."""
    if config.signature_secret:
        return "active"
    if config.signature_secret_hash:
        return "needs_secret"
    return "none"


def _signing_secret(config: WebhookConfig) -> str | None:
    """Plaintext secret, or None when the delivery must go out unsigned."""
    if config.signature_secret:
        return config.signature_secret
    if config.signature_secret_hash:
        logger.warning(
            "webhook %s has only a legacy signature hash; re-enter the secret "
            "to enable HMAC (unsigned until then)",
            config.id,
        )
    return None


def _public(config: WebhookConfig) -> dict[str, Any]:
    """Public representation; header values and the secret are never exposed."""
    headers = json.loads(config.headers or "{}")
    return {
        "id": config.id,
        "name": config.name,
        "url": config.url,
        "event": config.event.value,
        "headers": {key: "***" for key in headers},
        "max_retries": config.max_retries,
        "active": config.active,
        "signature_status": _signature_status(config),
        "created_at": config.created_at.isoformat(),
    }


# --- API routes (wired in the lifespan with the app's session factory) -------

def register_routes(app, session_factory=None) -> None:
    """Attach the webhook CRUD + delivery-listing routes to a FastAPI app.

    Uses the repo's standard pattern: each endpoint reads the session factory
    from ``request.app.state`` (no dependency-injection helper), exactly like
    the feedback/scopes routers. ``session_factory`` is kept for tests that
    wire an explicit factory instead of the app state.

    TASK-24: these routes carry the same auth dependencies as every other
    data router. Webhooks are the MOST sensitive surface (they can exfiltrate
    third-party metadata to an arbitrary URL), so the wiring is unconditional
    here too: auth disabled → no-op dependencies (v0.5.0 behavior); auth
    enabled → 401 without a session, CSRF + operator role on mutations,
    and the operator role on GET as well (TASK-31: webhook config is an
    integration secret, not a viewer read).
    """
    # Late import: app.py imports webhooks (for the dispatcher), so a module-
    # level import of metatracer.api.app from here would cycle.
    from metatracer.api import auth as auth_api

    auth_deps = [
        Depends(auth_api.get_current_user),
        Depends(auth_api.require_operator_action),
        Depends(auth_api.require_operator),
    ]

    async def _list(request: Request) -> list[dict[str, Any]]:
        factory = session_factory or request.app.state.session_factory
        async with factory() as session:
            configs = await WebhookConfigRepository(session).list_all()
        return [_public(cfg) for cfg in configs]

    async def _create(request: Request, body: WebhookCreate) -> dict[str, Any]:
        factory = session_factory or request.app.state.session_factory
        config = WebhookConfig(
            name=body.name or "",
            url=str(body.url),
            event=body.event,
            headers=json.dumps(body.headers or {}),
            max_retries=body.max_retries,
            active=body.active,
        )
        _apply_signature_secret(config, body.signature_secret)
        async with factory() as session:
            created = await WebhookConfigRepository(session).create(config)
        return _public(created)

    async def _update(
        webhook_id: str, body: WebhookUpdate, request: Request
    ) -> dict[str, Any]:
        factory = session_factory or request.app.state.session_factory
        async with factory() as session:
            repo = WebhookConfigRepository(session)
            cfg = await repo.get(webhook_id)
            if cfg is None:
                raise HTTPException(status_code=404, detail="webhook not found")
            if body.url is not None:
                cfg.url = str(body.url)
            if body.name is not None:
                cfg.name = body.name
            if body.event is not None:
                cfg.event = body.event
            if body.headers is not None:
                cfg.headers = json.dumps(body.headers)
            if body.max_retries is not None:
                cfg.max_retries = body.max_retries
            if body.active is not None:
                cfg.active = body.active
            _apply_signature_secret(cfg, body.signature_secret)
            updated = await repo.update(cfg)
        return _public(updated)

    async def _delete(webhook_id: str, request: Request) -> Response:
        factory = session_factory or request.app.state.session_factory
        async with factory() as session:
            repo = WebhookConfigRepository(session)
            cfg = await repo.get(webhook_id)
            if cfg is None:
                raise HTTPException(status_code=404, detail="webhook not found")
            await repo.delete(webhook_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def _deliveries(webhook_id: str, request: Request) -> list[dict[str, Any]]:
        factory = session_factory or request.app.state.session_factory
        async with factory() as session:
            config_repo = WebhookConfigRepository(session)
            if await config_repo.get(webhook_id) is None:
                raise HTTPException(status_code=404, detail="webhook not found")
            rows = await WebhookDeliveryRepository(session).list_by_webhook(webhook_id)
        return [
            {
                "id": d.id,
                "run_id": d.run_id,
                "status": d.status.value,
                "attempts": d.attempts,
                "max_retries": d.max_retries,
                "status_code": d.status_code,
                "last_error": d.last_error,
                "created_at": d.created_at.isoformat(),
            }
            for d in rows
        ]

    app.add_api_route(
        "/api/webhooks",
        _list,
        methods=["GET"],
        name="list_webhooks",
        dependencies=auth_deps,
    )
    app.add_api_route(
        "/api/webhooks",
        _create,
        methods=["POST"],
        name="create_webhook",
        dependencies=auth_deps,
    )
    app.add_api_route(
        "/api/webhooks/{webhook_id}",
        _update,
        methods=["PUT"],
        name="update_webhook",
        dependencies=auth_deps,
    )
    app.add_api_route(
        "/api/webhooks/{webhook_id}",
        _delete,
        methods=["DELETE"],
        name="delete_webhook",
        dependencies=auth_deps,
    )
    app.add_api_route(
        "/api/webhooks/{webhook_id}/deliveries",
        _deliveries,
        methods=["GET"],
        name="list_webhook_deliveries",
        dependencies=auth_deps,
    )


# --- Dispatcher ---------------------------------------------------------------

class _RedactHttpxHeaders(logging.Filter):
    """Drop httpx/httpcore debug lines that would print webhook header values.

    Operator headers may carry tokens (TASK-33, review R4). The status code
    path does not need those lines.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage().lower()
        if "header" in text or "authorization" in text or "cookie" in text:
            return False
        return True


class WebhookDispatcher:
    """Persists relay-buffer rows and delivers terminal-run events outbound.

    Injected into the orchestrator like :class:`NotificationBus`: the pipeline
    never knows it exists. ``None`` or an empty bus is a complete no-op.
    """

    def __init__(
        self,
        session_factory,
        *,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        max_backoff: float = 300.0,
        guard: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        # Anti-SSRF guard for the outbound POSTs (invariant rule 7 applies to
        # egress too): same NetworkSafetyGuard as the rest of the app, wired by
        # the API lifespan. Test doubles may pass a stand-in.
        self._guard = guard
        # Strong references to the fire-and-forget send tasks (the event loop
        # only weakly references tasks; dropping them could collect a pending
        # delivery attempt).
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue_terminal(
        self,
        run_id: str,
        status: RunStatus,
        *,
        target: str | None = None,
        total_assets: int = 0,
        total_findings: int = 0,
        new_findings: int = 0,
        resolved_findings: int = 0,
        severity_up_count: int = 0,
        executive_summary: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Render + persist one delivery row per matching active webhook.

        Idempotent per ``(webhook_id, run_id)``; a missing run report or a
        broken consumer never raises (inviolable rule 5). The actual HTTP send
        is scheduled as a background task.
        """
        if status not in (RunStatus.completed, RunStatus.failed, RunStatus.aborted):
            return
        # Opportunistic recovery of a previous process's pending deliveries
        # before we add new ones (the relay buffer is idempotent).
        await self.recover_pending()
        async with self._session_factory() as session:
            configs = await WebhookConfigRepository(session).list_active_by_event(status)
        if not configs:
            return
        payload = await self._build_payload(
            run_id,
            status,
            target,
            total_assets,
            total_findings,
            new_findings,
            resolved_findings,
            severity_up_count,
            executive_summary,
            error_message,
        )
        # Contract guard: only the fixed keys ever go out. A future renderer
        # that adds keys would fail here (defense in depth against accidental
        # metadata leaks), never send an unexpected document.
        if set(payload) - set(PAYLOAD_KEYS):
            logger.warning(
                "webhook payload has unexpected keys; dropping them before delivery"
            )
            payload = {key: payload[key] for key in PAYLOAD_KEYS if key in payload}
        for cfg in configs:
            async with self._session_factory() as session:
                delivery_repo = WebhookDeliveryRepository(session)
                exists = await delivery_repo.get_by_webhook_run(cfg.id, run_id)
                if exists is not None:
                    continue
                delivery = WebhookDelivery(
                    webhook_id=cfg.id,
                    run_id=run_id,
                    status=WebhookDeliveryStatus.pending,
                    attempts=0,
                    max_retries=min(cfg.max_retries, self._max_retries),
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
                await delivery_repo.create(delivery)
            # Fire-and-forget: never block the scan on remote endpoints. The
            # strong reference in self._tasks keeps the task alive until it
            # completes; the done-callback discards it.
            task = asyncio.create_task(self._attempt(cfg.id, run_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _build_payload(
        self,
        run_id: str,
        status: RunStatus,
        target: str | None,
        total_assets: int,
        total_findings: int,
        new_findings: int,
        resolved_findings: int,
        severity_up_count: int,
        executive_summary: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        """Flat scalar JSON body; keys fixed by PAYLOAD_KEYS."""
        from metatracer.db.repositories import RunRepository

        run_ref = run_id
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
            if run is not None and run.run_ref:
                run_ref = run.run_ref
        return {
            "run_id": run_id,
            "run_ref": run_ref,
            "event": status.value,
            "target": target,
            "total_assets": total_assets,
            "total_findings": total_findings,
            "new_findings": max(new_findings, 0),
            "resolved_findings": max(resolved_findings, 0),
            "severity_up_count": max(severity_up_count, 0),
            "executive_summary": (executive_summary or "")[:300],
            "error_message": sanitize_for_log(error_message or "", max_length=300) or None,
        }

    async def recover_pending(self) -> None:
        """Re-enqueue deliveries left pending by a previous process (restart).

        Relay-buffer rows are idempotent per ``(webhook_id, run_id)``, so a
        replay after a crash is safe: the recipient may receive a duplicate
        POST but never a wrong one. Called opportunistically by the orchestrator
        when a run terminal event is about to be enqueued (a configured webhook
        is a strong signal the operator expects retries).
        """
        async with self._session_factory() as session:
            pending = await WebhookDeliveryRepository(session).list_pending()
        for delivery in pending:
            task = asyncio.create_task(self._attempt(delivery.webhook_id, delivery.run_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        """Cancel in-flight send tasks (server shutdown).

        Delivery rows are already persisted (the relay buffer), so an
        interrupted attempt is safe: the next ``list_pending`` sweep retries
        it from the database.
        """
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def sweep_due_retries(self) -> int:
        """Retry deliveries whose ``next_retry_at`` has passed.

        Independent of new scans (TASK-33). A first attempt still in flight
        has ``next_retry_at is None`` and is left to the task that owns it.
        """
        async with self._session_factory() as session:
            pending = await WebhookDeliveryRepository(session).list_pending()
        due = [row for row in pending if row.next_retry_at is not None]
        for delivery in due:
            task = asyncio.create_task(self._attempt(delivery.webhook_id, delivery.run_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return len(due)

    async def _attempt(self, webhook_id: str, run_id: str) -> None:
        """One attempt; schedules retries with backoff when the send fails."""
        async with self._session_factory() as session:
            delivery = await WebhookDeliveryRepository(session).get_by_webhook_run(
                webhook_id, run_id
            )
            config = await WebhookConfigRepository(session).get(webhook_id)
        if delivery is None or config is None or not config.active:
            return
        if delivery.status in (WebhookDeliveryStatus.succeeded, WebhookDeliveryStatus.rejected):
            return
        if delivery.next_retry_at is not None and time.time() < delivery.next_retry_at:
            return
        delivery.attempts += 1
        try:
            payload = json.loads(delivery.payload_json)
        except json.JSONDecodeError:
            await self._update_delivery(
                delivery, WebhookDeliveryStatus.failed, error="corrupt cached payload"
            )
            return

        status_code, error = await self._send(config, payload)

        if error is None and status_code is not None and 200 <= status_code < 300:
            delivery.status_code = status_code
            await self._update_delivery(delivery, WebhookDeliveryStatus.succeeded)
            return
        if error is None and status_code is not None and 400 <= status_code < 500:
            delivery.status_code = status_code
            await self._update_delivery(
                delivery,
                WebhookDeliveryStatus.rejected,
                error=f"HTTP {status_code}: recipient rejected the payload",
            )
            return
        if delivery.attempts >= delivery.max_retries:
            await self._update_delivery(
                delivery,
                WebhookDeliveryStatus.failed,
                error=error or f"HTTP {status_code}",
            )
            return
        delay = min(self._max_backoff, self._base_backoff * (2 ** (delivery.attempts - 1)))
        delivery.next_retry_at = time.time() + delay
        delivery.last_error = error or f"HTTP {status_code}"
        await self._update_delivery(delivery, WebhookDeliveryStatus.pending)

    async def _send(
        self, config: WebhookConfig, payload: dict[str, Any]
    ) -> tuple[int | None, str | None]:
        """POST the payload to the configured HTTPS endpoint.

        Webhook URLs are operator-targeted egress to third-party channels
        (Slack/Discord/Teams/…), **not** assets of the run's scope, so they do
        not go through ``safe_httpx_request`` (that gateway requires a
        confirmed scope and would reject an out-of-scope host). Instead we use
        a dedicated, locked-down client:

        - HTTPS only (validated at write time, re-checked here);
        - no redirects (a redirecting webhook endpoint is a misconfiguration);
        - short timeouts so a dead endpoint frees the worker fast;
        - the response body is never read — only the status code matters;
        - the send is wrapped so a failure is an error string, never an
          exception that could escape to the pipeline.
        """
        headers = {
            "User-Agent": "MetaTracer-webhook/1.0",
            "Content-Type": "application/json",
            **(json.loads(config.headers or "{}") or {}),
        }
        body = webhook_body_bytes(payload)
        secret = _signing_secret(config)
        if secret:
            # Sign the bytes we are about to send, not a second serialization.
            timestamp = str(int(time.time()))
            mac = hmac.new(
                secret.encode("utf-8"),
                timestamp.encode("ascii") + b"." + body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-MetaTracer-Timestamp"] = timestamp
            headers["X-MetaTracer-Signature"] = f"sha256={mac}"
        try:
            import httpx

            parsed_scheme = config.url.lower().split(":", 1)[0]
            if parsed_scheme != "https":
                return None, "webhook URL must use HTTPS (refused before any socket)"
            parsed = urlsplit(config.url)
            host = parsed.hostname or ""
            port = parsed.port or 443
            # Invariant rule 7 applies to egress as much as to ingress: never
            # POST to loopback/private/link-local/cloud-metadata addresses,
            # even though the URL is operator-supplied. The guard resolves
            # DNS and mistakes a webhook host for a scan asset are caught here
            # before any socket opens; a bare IP is checked directly.
            if self._guard is not None:
                try:
                    await self._guard.check(host, port)
                except SecurityViolationError as exc:  # noqa: PERF203
                    return None, f"webhook target rejected ({sanitize_for_log(exc)})"
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
            redactor = _RedactHttpxHeaders()
            httpx_logger = logging.getLogger("httpx")
            httpcore_logger = logging.getLogger("httpcore")
            httpx_logger.addFilter(redactor)
            httpcore_logger.addFilter(redactor)
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    headers=headers,
                    # Same proxy bypass as safe_httpx_request (TASK-27, P0-1).
                    trust_env=False,
                ) as client:
                    response = await client.post(config.url, content=body)
                    # Body never read: we only need the status code.
                    return response.status_code, None
            finally:
                httpx_logger.removeFilter(redactor)
                httpcore_logger.removeFilter(redactor)
        except Exception as exc:
            return None, sanitize_for_log(exc, max_length=300)

    async def _update_delivery(
        self,
        delivery: WebhookDelivery,
        status_: WebhookDeliveryStatus,
        *,
        error: str | None = None,
    ) -> None:
        delivery.status = status_
        if error is not None:
            delivery.last_error = sanitize_for_log(error, max_length=300)
            delivery.next_retry_at = None
        async with self._session_factory() as session:
            await WebhookDeliveryRepository(session).update(delivery)