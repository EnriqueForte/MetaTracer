"""HTML pages (TASK-06, subtask 6.4): the scan wizard and the run dashboard.

The shells render with Jinja2 (autoescape always on, never ``|safe``); all
dynamic data flows through the JSON API and is rendered by Alpine.js via
``x-text``/``textContent`` — never ``x-html``/``innerHTML`` — so target-
controlled content cannot inject markup.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from metatracer import __version__
from metatracer.api import auth as auth_api
from metatracer.api.auth import CSRF_COOKIE_NAME
from metatracer.db.models import ReasoningDepth

router = APIRouter(include_in_schema=False)


async def _current_user(request: Request) -> dict | None:
    """The signed-in user as a plain dict, or ``None`` (anonymous / auth off).

    The middleware already validated the session for non-exempt pages, so
    this re-resolution is one indexed lookup per page render; it reuses the
    same ``_resolve_session`` primitive instead of duplicating the query.
    With auth OFF there is no session model and this returns ``None`` fast.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.auth_enabled:
        return None
    try:
        user = await auth_api._resolve_session(request)
    except auth_api._InvalidSession:
        return None
    return {"username": user.username, "role": user.role.value}


async def _page_context(request: Request) -> dict:
    """Common template context for every page shell (TASK-24, TASK-25).

    ``auth_enabled`` drives the Sign out button; ``csrf_token`` (read from
    the double-submit cookie) feeds the <meta> tag that the shared JS reads
    for unsafe fetches. ``current_user`` (TASK-25) drives the "Signed in as"
    header line and the Users nav visibility (operator-only when auth is on).
    The session cookie value NEVER enters the template context — only the
    unrelated CSRF token does.
    """
    settings = getattr(request.app.state, "settings", None)
    auth_enabled = bool(settings and settings.auth_enabled)
    return {
        "version": __version__,
        "auth_enabled": auth_enabled,
        "current_user": await _current_user(request) if auth_enabled else None,
        "csrf_token": request.cookies.get(CSRF_COOKIE_NAME, "") if auth_enabled else "",
    }


def _ensure_pre_session_csrf(request: Request, response) -> None:
    """Issue the throwaway CSRF cookie for pre-session page renders (TASK-25).

    Shared by /login, /register and /setup: the first render of any page
    whose form posts credentials must hand the browser the double-submit
    cookie. Delegates to ``auth_api._ensure_csrf_cookie`` so the page logic
    stays in lockstep with the endpoint-side pre-session check.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.auth_enabled:
        return
    auth_api._ensure_csrf_cookie(request, response, settings)


@router.get("/runs", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    """Local run history (TASK-08). Data loads from GET /api/runs via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "history.html", await _page_context(request)
    )


@router.get("/scopes", response_class=HTMLResponse)
async def scopes_page(request: Request) -> HTMLResponse:
    """Scope manager (TASK-10, v2.0). Data loads from GET /api/scopes via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "scopes.html", await _page_context(request)
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Aggregated dashboard (TASK-11, v2.0). Data loads from GET /api/stats via Alpine."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "dashboard.html", await _page_context(request)
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Scan wizard: targets, scope domains, depth and the blocking scope modal."""
    context = await _page_context(request)
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
    return templates.TemplateResponse(
        request, "run.html", await _page_context(request)
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Login page (TASK-24). The middleware redirects everyone who needs it
    here; when auth is disabled this page is simply never linked.

    The login POST itself is CSRF-protected (pre-session double-submit): the
    first render issues the throwaway CSRF cookie (random, session-
    independent) that the form echoes back in the X-CSRF-Token header.
    """
    context = await _page_context(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(request, "login.html", context)
    _ensure_pre_session_csrf(request, response)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Invitation-redeem page (TASK-25). 404 when auth is off — the page
    never becomes a discoverable surface on unauthenticated installations.

    Standalone like login.html (no base.html: the notifications bell polls
    the API and an anonymous visitor would 401 on every load). Issues the
    pre-session CSRF cookie exactly like the login page.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.auth_enabled:
        from fastapi import HTTPException, status

        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "authentication is disabled on this installation",
        )
    context = await _page_context(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(request, "register.html", context)
    _ensure_pre_session_csrf(request, response)
    return response


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    """First-run setup page (TASK-25). Three gates, in contract order:

    - auth off, or the initial operator was provisioned from
      ``METATRACER_AUTH_PASSWORD`` → 404 (setup flow disabled there);
    - setup mode already consumed (users exist → ``setup_token`` is None)
      → redirect to /login (the installation is provisioned; a logged-out
      visitor just sees the normal login);
    - otherwise render the setup form (the middleware exempts this path).
    """
    settings = getattr(request.app.state, "settings", None)
    if (
        settings is None
        or not settings.auth_enabled
        or settings.auth_password.get_secret_value()
    ):
        from fastapi import HTTPException, status

        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "setup is not available for this installation",
        )
    if getattr(request.app.state, "setup_token", None) is None:
        return RedirectResponse("/login", status_code=307)
    context = await _page_context(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(request, "setup.html", context)
    _ensure_pre_session_csrf(request, response)
    return response


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request) -> HTMLResponse:
    """User & invitation admin panel (TASK-25). The shell renders
    unconditionally: the middleware already bounced anonymous visitors to
    /login, and the page JS covers the 401/403 data states (viewer sees its
    read-only posture, operator gets the full admin controls)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "users.html", await _page_context(request)
    )
