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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from metatracer import __version__
from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.agents.pipeline import AgentPipeline
from metatracer.api import feedback, knowledge, notifications, pages, runs, scopes, stats
from metatracer.core.config import Settings
from metatracer.core.logging import configure_logging
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.reports.builder import DEFAULT_REPORTS_DIR
from metatracer.services.notifications import NotificationBus
from metatracer.services.orchestrator import ScanOrchestratorService
from metatracer.services.progress import ProgressBus

_PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = _PACKAGE_DIR / "templates"
STATIC_DIR = _PACKAGE_DIR / "static"


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
        app.state.orchestrator = ScanOrchestratorService(
            app.state.session_factory,
            settings,
            notifications=app.state.notifications_bus,
            agents=agents,
        )
        app.state.reports_dir = reports_dir
        app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
        yield
        await app.state.orchestrator.shutdown()
        await engine.dispose()

    app = FastAPI(
        title="MetaTracer",
        version=__version__,
        description=(
            "Sensitive metadata discovery for authorized security audits. "
            "No authentication in v1.0: bind to localhost / trusted networks only."
        ),
        lifespan=lifespan,
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe for the Docker HEALTHCHECK (TASK-07, subtask 7.3.5).

        Deliberately stateless: it reveals no configuration, counters or
        version beyond what the API schema already exposes.
        """
        return {"status": "ok"}

    app.include_router(runs.router)
    app.include_router(scopes.router)
    app.include_router(stats.router)
    app.include_router(notifications.router)
    app.include_router(feedback.router)
    app.include_router(knowledge.router)
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
