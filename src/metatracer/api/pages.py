"""HTML pages (TASK-06, subtask 6.4): the scan wizard and the run dashboard.

The shells render with Jinja2 (autoescape always on, never ``|safe``); all
dynamic data flows through the JSON API and is rendered by Alpine.js via
``x-text``/``textContent`` — never ``x-html``/``innerHTML`` — so target-
controlled content cannot inject markup.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from metatracer import __version__
from metatracer.api.auth import CSRF_COOKIE_NAME
from metatracer.db.models import ReasoningDepth

router = APIRouter(include_in_schema=False)


def _page_context(request: Request) -> dict:
    """Common template context for every page shell (TASK-24).

    ``auth_enabled`` drives the Sign out button; ``csrf_token`` (read from
    the double-submit cookie) feeds the <meta> tag that the shared JS reads
    for unsafe fetches. The session cookie value NEVER enters the template
    context — only the unrelated CSRF token does.
    """
    settings = getattr(request.app.state, "settings", None)
    auth_enabled = bool(settings and settings.auth_enabled)
    return {
        "version": __version__,
        "auth_enabled": auth_enabled,
        "csrf_token": request.cookies.get(CSRF_COOKIE_NAME, "") if auth_enabled else "",
    }


@router.get("/runs", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    """Local run history (TASK-08). Data loads from GET /api/runs via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "history.html", _page_context(request))


@router.get("/scopes", response_class=HTMLResponse)
async def scopes_page(request: Request) -> HTMLResponse:
    """Scope manager (TASK-10, v2.0). Data loads from GET /api/scopes via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "scopes.html", _page_context(request))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Aggregated dashboard (TASK-11, v2.0). Data loads from GET /api/stats via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html", _page_context(request))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Scan wizard: targets, scope domains, depth and the blocking scope modal."""
    context = _page_context(request)
    context["depths"] = [depth.value for depth in ReasoningDepth]
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: str) -> HTMLResponse:
    """Run results page shell.

    The shell renders unconditionally; the dashboard JS takes the run_id from
    the URL and covers every data state (loading, unknown run, in progress,
    failed, zero findings, populated) through the API.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "run.html", _page_context(request))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Login page (TASK-24). The middleware redirects everyone who needs it
    here; when auth is disabled this page is simply never linked.

    The login POST itself is CSRF-protected (pre-session double-submit): the
    first render issues the throwaway CSRF cookie (random, session-
    independent) that the form echoes back in the X-CSRF-Token header.
    """
    settings = getattr(request.app.state, "settings", None)
    context = _page_context(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(request, "login.html", context)
    if settings is not None and settings.auth_enabled and not request.cookies.get(
        CSRF_COOKIE_NAME
    ):
        import secrets

        from metatracer.api.auth import _SESSION_TOKEN_BYTES

        response.set_cookie(
            CSRF_COOKIE_NAME,
            secrets.token_urlsafe(_SESSION_TOKEN_BYTES),
            max_age=settings.session_ttl_seconds,
            samesite="lax",
            path="/",
            httponly=False,
            secure=False,
        )
    return response
