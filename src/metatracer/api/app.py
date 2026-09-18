"""FastAPI application factory (TASK-06, subtask 6.3).

Security posture of v1.0: there is NO authentication, so the only protection
is the bind address — ``settings.bind_host`` defaults to ``127.0.0.1`` and the
server is meant for localhost / a trusted network only. The Docker image sets
``METATRACER_BIND_HOST=0.0.0.0`` deliberately (TASK-07); nothing else should.

The lifespan wires the shared stack once — engine, schema, session factory,
ProgressBus and the single ScanOrchestratorService — stores it on
``app.state`` and disposes it on shutdown. Templates and static assets load
from paths relative to this module so the installed package works from any
working directory (see ``[tool.setuptools.package-data]``).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from metatracer import __version__
from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.agents.pipeline import AgentPipeline
from metatracer.api import auth as auth_api
from metatracer.api import feedback, knowledge, notifications, pages, runs, scopes, stats
from metatracer.api.webhooks import WebhookDispatcher
from metatracer.api.webhooks import register_routes as register_webhook_routes
from metatracer.core.config import Settings
from metatracer.core.logging import configure_logging
from metatracer.core.ratelimit import ApiRateLimiter, enforce_body_limit
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.reports.builder import DEFAULT_REPORTS_DIR
from metatracer.services.notifications import NotificationBus
from metatracer.services.orchestrator import ScanOrchestratorService
from metatracer.services.progress import ProgressBus
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
#   bounded: one subscriber per run id and it closes on terminal events.
_RATE_LIMIT_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/static/",
)

# TASK-24: paths reachable without a session when auth is enabled. /login is
# the login page itself; /api/auth/* is the pre-auth surface (login posts
# credentials, me/logout self-diagnose); /api/health stays stateless.
_PAGE_AUTH_EXEMPT: frozenset[str] = frozenset({"/login", "/api/health"})


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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
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
        register_webhook_routes(app, app.state.session_factory)
        app.state.reports_dir = reports_dir
        app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
        # v2.3 performance slice: API-edge rate limit + body-size cap. Shared
        # with the fastapi routes created below; HEALTH and STATIC are exempt
        # (see _is_rate_limit_exempt).
        app.state.rate_limiter = ApiRateLimiter(settings.api_rate_limit_per_minute)
        app.state.max_request_body_bytes = settings.max_request_body_bytes
        # TASK-24 (v3.0, Eje C): provision the initial operator BEFORE any
        # request can hit an endpoint (fail-closed on missing/short password).
        await auth_api.ensure_default_user(app.state.session_factory, settings)
        yield
        await app.state.webhook_dispatcher.shutdown()
        await app.state.orchestrator.shutdown()
        await engine.dispose()

    app = FastAPI(
        title="MetaTracer",
        version=__version__,
        description=(
            "Sensitive metadata discovery for authorized security audits. "
            "Authentication is optional (METATRACER_AUTH_ENABLED): when off, "
            "bind to localhost / trusted networks only."
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
                length = request.headers.get("content-length")
                if length is not None and length.isdigit():
                    enforce_body_limit(int(length), max_body)
            # TASK-24 (v3.0, Eje C): HTML pages are browser surfaces, not API
            # consumers — an unauthenticated page hit redirects to /login
            # instead of answering 401 JSON. Auth-disabled deployments skip
            # this entirely. /login itself is the login page and stays open.
            path = request.url.path
            settings: Settings | None = getattr(request.app.state, "settings", None)
            if (
                settings is not None
                and settings.auth_enabled
                and path not in _PAGE_AUTH_EXEMPT
                and not path.startswith("/static/")
                and not path.startswith("/api/")
                and request.method in ("GET", "HEAD")
            ):
                try:
                    await auth_api._resolve_session(request)
                except auth_api._InvalidSession:
                    return RedirectResponse("/login", status_code=307)
            return await call_next(request)
        except HTTPException as exc:
            # Middleware-raised HTTPExceptions do not flow through FastAPI's
            # exception handlers outside the router, so render the JSON here.
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe for the Docker HEALTHCHECK (TASK-07, subtask 7.3.5).

        Deliberately stateless: it reveals no configuration, counters or
        version beyond what the API schema already exposes.
        """
        return {"status": "ok"}

    # TASK-24 (v3.0, Eje C): every data router takes the auth dependencies
    # UNCONDITIONALLY. When auth is disabled (default) they no-op and the
    # behavior is exactly v0.5.0; when enabled, reads require a session
    # (401), and mutations additionally require CSRF + the operator role
    # (403). get_current_user is resolved once per request (FastAPI caches
    # dependency results), so require_operator_action reusing it as a
    # sub-dependency costs nothing extra. See metatracer.api.auth.
    data_deps = [Depends(auth_api.get_current_user)]
    action_deps = [Depends(auth_api.require_operator_action)]

    app.include_router(runs.router, dependencies=data_deps + action_deps)
    app.include_router(scopes.router, dependencies=data_deps + action_deps)
    app.include_router(stats.router, dependencies=data_deps)
    app.include_router(notifications.router, dependencies=data_deps + action_deps)
    app.include_router(feedback.router, dependencies=data_deps + action_deps)
    app.include_router(knowledge.router, dependencies=data_deps + action_deps)
    app.include_router(auth_api.router)  # login/logout/me are pre-auth by design
    app.include_router(pages.router)  # pages gate themselves (redirect to /login)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
