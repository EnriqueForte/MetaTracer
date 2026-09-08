"""HTML pages (TASK-06, subtask 6.4): the scan wizard and the run dashboard.

The shells render with Jinja2 (autoescape always on, never ``|safe``); all
dynamic data flows through the JSON API and is rendered by Alpine.js via
``x-text``/``textContent`` — never ``x-html``/``innerHTML`` — so target-
controlled content cannot inject markup.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from metatracer import __version__
from metatracer.db.models import ReasoningDepth

router = APIRouter(include_in_schema=False)


@router.get("/runs", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    """Local run history (TASK-08). Data loads from GET /api/runs via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "history.html", {"version": __version__})


@router.get("/scopes", response_class=HTMLResponse)
async def scopes_page(request: Request) -> HTMLResponse:
    """Scope manager (TASK-10, v2.0). Data loads from GET /api/scopes via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "scopes.html", {"version": __version__})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Aggregated dashboard (TASK-11, v2.0). Data loads from GET /api/stats via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html", {"version": __version__})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Scan wizard: targets, scope domains, depth and the blocking scope modal."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "index.html",
        {"version": __version__, "depths": [depth.value for depth in ReasoningDepth]},
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: str) -> HTMLResponse:
    """Run results page shell.

    The shell renders unconditionally; the dashboard JS takes the run_id from
    the URL and covers every data state (loading, unknown run, in progress,
    failed, zero findings, populated) through the API.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "run.html", {"version": __version__})
