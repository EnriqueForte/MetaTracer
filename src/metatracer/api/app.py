"""FastAPI application factory (TASK-06, subtask 6.3).

Security posture of v1.0: there is NO authentication unless
``METATRACER_AUTH_ENABLED`` is set, so a loopback bind is the default
protection — ``settings.bind_host`` defaults to ``127.0.0.1``. The Docker
image binds ``0.0.0.0`` and refuses to start while auth is off (TASK-27)
unless ``METATRACER_ALLOW_UNAUTHENTICATED_BIND`` is set.

The lifespan wires the shared stack once — engine, schema, session factory,
ProgressBus and the single ScanOrchestratorService — stores it on
``app.state`` and disposes it on shutdown. Templates and static assets load
from paths relative to this module so the installed package works from any
working directory (see ``[tool.setuptools.package-data]``).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from metatracer import __version__
from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.agents.pipeline import AgentPipeline
from metatracer.api import auth as auth_api
from metatracer.api import compare, feedback, knowledge, notifications, runs, scopes, stats, users
from metatracer.api.pages import router as pages_router
from metatracer.api.security_headers import apply_security_headers
from metatracer.api.webhooks import WebhookDispatcher
from metatracer.api.webhooks import register_routes as register_webhook_routes
from metatracer.core.config import Settings, enforce_loopback_test_only
from metatracer.core.logging import configure_logging
from metatracer.core.ratelimit import (
    ApiRateLimiter,
    cap_request_body,
    enforce_body_limit,
    reject_bad_content_length,
)
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.extractors.ingest import sweep_stale_tempfiles
from metatracer.reports.builder import DEFAULT_REPORTS_DIR
from metatracer.services.notifications import NotificationBus
from metatracer.services.orchestrator import ScanOrchestratorService
from metatracer.services.progress import ProgressBus
from metatracer.services.retention import prune_expired_runs
from metatracer.services.watch import DeltaReporter

_PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"

# Paths that are exempt from the API-edge rate limit (they are either
# liveness probes consumed by the Docker HEALTHCHECK or bounded, short-lived
# server resources):
# - /api/health is deliberately stateless and cheap; rate-limiting it would
#   make the container's OWN healthcheck fail under load.
# - /static/* is served from memory by Starlette, no database, no pipeline;
#   the browser legitimately issues many parallel requests for it.
# - /api/runs/*/stream is the SSE stream: the browser holds it open for the
#   whole scan, so counting keep-alives against a client's budget would break
#   the dashboard under a normal single scan. The stream endpoint is itself
#   bounded: each subscriber closes on a terminal event. Several clients may
#   watch the same run; the bus fans out to every queue.
_RATE_LIMIT_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/ready",
    "/static/",
)

_RETENTION_INTERVAL_SECONDS = 24 * 3600
_WEBHOOK_RETRY_SECONDS = 15


async def _retention_loop(app: FastAPI) -> None:
    """Delete expired terminal runs at startup and once a day (TASK-30)."""
    logger = logging.getLogger("metatracer.api.retention")
    while True:
        settings: Settings = app.state.settings
        try:
            await prune_expired_runs(
                app.state.session_factory,
                retention_days=settings.retention_days,
                reports_dir=app.state.reports_dir,
            )
        except Exception:
            logger.warning("retention sweep failed", exc_info=True)
        await asyncio.sleep(_RETENTION_INTERVAL_SECONDS)


async def _webhook_retry_loop(app: FastAPI) -> None:
    """Retry due webhook deliveries without waiting for another scan (TASK-33)."""
    logger = logging.getLogger("metatracer.api.webhooks")
    while True:
        try:
            await app.state.webhook_dispatcher.sweep_due_retries()
        except Exception:
            logger.warning("webhook retry sweep failed", exc_info=True)
        await asyncio.sleep(_WEBHOOK_RETRY_SECONDS)


def _as_http_exception(exc: BaseException) -> HTTPException | None:
    """HTTPException raised directly, or the single one inside a task group.

    BaseHTTPMiddleware reads the body in a child task. A cap raised from
    ``receive`` therefore surfaces as an ``ExceptionGroup`` (TASK-31).
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        return _as_http_exception(exc.exceptions[0])
    return None


def _is_rate_limit_exempt(path: str) -> bool:
    """True for health, static assets and SSE streams (see above)."""
    if path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES):
        return True
    return path.startswith("/api/runs/") and path.endswith("/stream")


def create_app(
    settings: Settings | None = None,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> FastAPI:
    """Build the FastAPI app; engine, schema and orchestrator wire up in the lifespan.

    ``reports_dir`` is where scans write and the export endpoint regenerates
    reports; tests point it at a tmp_path.
    """
    settings = settings if settings is not None else Settings()
    enforce_loopback_test_only(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        sweep_stale_tempfiles()
        engine = create_db_engine(settings.database_url)
        await init_db(engine)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.bus = ProgressBus()
        app.state.notifications_bus = NotificationBus()
        # TASK-14 (v2.1+): shared light-RAG retriever for the agent phase and
        # the /api/knowledge inspection endpoint. Lazy: the FTS5 index is
        # rebuilt on first use and cached for the process lifetime.
        app.state.knowledge_retriever = KnowledgeRetriever(engine, app.state.session_factory)
        agents = AgentPipeline(
            app.state.session_factory,
            settings,
            knowledge=app.state.knowledge_retriever,
        )
        # TASK-15 (v2.2): outbound webhook dispatcher. Shared with the
        # orchestrator exactly like the notification bus: it only reads
        # terminal run events and never blocks the scan on remote endpoints.
        # Carries the same anti-SSRF NetworkSafetyGuard as the ingestion
        # pipeline: egress obeys invariant rule 7 (loopback/private/link-local
        # blocked) just like ingress does.
        app.state.webhook_dispatcher = WebhookDispatcher(
            app.state.session_factory,
            guard=NetworkSafetyGuard(settings.allow_loopback),
        )
        # TASK-22 (v3.0, Eje A): deterministic delta reporter shared with the
        # orchestrator. A run launched with ``watch=True`` (the headless watch
        # loop) computes ``new_findings`` before the terminal webhook payload,
        # from either surface (CLI or API) — same reporter, both lifespans.
        app.state.delta_reporter = DeltaReporter(app.state.session_factory)
        app.state.orchestrator = ScanOrchestratorService(
            app.state.session_factory,
            settings,
            notifications=app.state.notifications_bus,
            webhooks=app.state.webhook_dispatcher,
            agents=agents,
            delta_reporter=app.state.delta_reporter,
        )
        await app.state.orchestrator.recover_interrupted_runs()
        register_webhook_routes(app, app.state.session_factory)
        app.state.reports_dir = reports_dir
        app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
        # v2.3 performance slice: API-edge rate limit + body-size cap. Shared
        # with the fastapi routes created below; HEALTH and STATIC are exempt
        # (see _is_rate_limit_exempt).
        app.state.rate_limiter = ApiRateLimiter(settings.api_rate_limit_per_minute)
        app.state.max_request_body_bytes = settings.max_request_body_bytes
        # TASK-24 (v3.0, Eje C): provision the initial operator BEFORE any
        # request can hit an endpoint. TASK-25 semantics: password in env ->
        # same provisioning; auth ON + no password + no users -> SETUP MODE
        # (the app boots; the one-shot setup token is logged to the console
        # once and parked in memory); users already exist -> no-op.
        app.state.setup_token = await auth_api.ensure_default_user(
            app.state.session_factory, settings
        )
        retention_task = asyncio.create_task(_retention_loop(app))
        webhook_retry_task = asyncio.create_task(_webhook_retry_loop(app))
        yield
        retention_task.cancel()
        webhook_retry_task.cancel()
        for task in (retention_task, webhook_retry_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        # R7: stop in-flight work, then release the engine.
        await app.state.webhook_dispatcher.shutdown()
        await app.state.orchestrator.shutdown()
        await engine.dispose()

    app = FastAPI(
        title="MetaTracer",
        version=__version__,
        description=(
            "Sensitive metadata discovery for authorized security audits. "
            "Authentication is optional on loopback (METATRACER_AUTH_ENABLED). "
            "A non-loopback bind refuses to start while auth is off unless "
            "METATRACER_ALLOW_UNAUTHENTICATED_BIND is set."
        ),
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def api_edge_guards(request: Request, call_next):
        """Rate-limit the API edge and cap request bodies (v2.3 perf slice).

        Runs before any route handler: a 413/429 here never touches the
        database, the pipeline or the LLM. Exempted paths (health, static,
        SSE streams) are defined in :func:`_is_rate_limit_exempt` — the SSE
        stream must not consume a client's budget while a scan runs.
        """
        limiter: ApiRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        max_body: int = getattr(request.app.state, "max_request_body_bytes", 0)
        try:
            if limiter is not None and not _is_rate_limit_exempt(request.url.path):
                await limiter.check(request)
            if not _is_rate_limit_exempt(request.url.path):
                declared = reject_bad_content_length(request.headers.get("content-length"))
                enforce_body_limit(declared, max_body)
                cap_request_body(request, max_body)
            response = await call_next(request)
            return apply_security_headers(response, request)
        except Exception as exc:
            # Middleware-raised HTTPExceptions do not flow through FastAPI's
            # exception handlers outside the router, so render the JSON here.
            # A body-cap raised inside BaseHTTPMiddleware's receive task is
            # wrapped in an ExceptionGroup; unwrap that single HTTPException.
            http_exc = _as_http_exception(exc)
            if http_exc is None:
                raise
            return apply_security_headers(
                JSONResponse(
                    status_code=http_exc.status_code,
                    content={"detail": http_exc.detail},
                    headers=http_exc.headers,
                ),
                request,
            )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe for the Docker HEALTHCHECK (TASK-07, subtask 7.3.5).

        Deliberately stateless: it reveals no configuration, counters or
        version beyond what the API schema already exposes.
        """
        return {"status": "ok"}

    @app.get("/api/ready")
    async def ready(request: Request) -> dict[str, str]:
        """Readiness: the database answers. Liveness stays on ``/api/health``."""
        from sqlalchemy import text

        try:
            async with request.app.state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ok"}

    # TASK-24 (v3.0, Eje C): every data router takes the auth dependencies
    # UNCONDITIONALLY. When auth is disabled (default) they no-op and the
    # behavior is exactly v0.5.0; when enabled, reads require a session
    # (401), and mutations additionally require CSRF + the operator role
    # (403). Admin reads (users, invitations) also require the operator role
    # on GET (TASK-31): require_operator_action allows any authenticated
    # reader on safe methods. get_current_user is resolved once per request.
    data_deps = [Depends(auth_api.get_current_user)]
    action_deps = [Depends(auth_api.require_operator_action)]
    operator_deps = [Depends(auth_api.require_operator)]

    app.include_router(runs.router, dependencies=data_deps + action_deps)
    app.include_router(scopes.router, dependencies=data_deps + action_deps)
    app.include_router(stats.router, dependencies=data_deps)
    app.include_router(compare.router, dependencies=data_deps)
    app.include_router(notifications.router, dependencies=data_deps + action_deps)
    app.include_router(feedback.router, dependencies=data_deps + action_deps)
    app.include_router(knowledge.router, dependencies=data_deps + action_deps)
    app.include_router(auth_api.router)  # login/logout/me/setup/register are pre-auth by design
    app.include_router(users.router, dependencies=data_deps + action_deps + operator_deps)
    app.include_router(
        users.invitations_router, dependencies=data_deps + action_deps + operator_deps
    )
    app.include_router(pages_router)  # pages gate themselves (redirect to /login)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
