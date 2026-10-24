"""Browser security headers for API responses (T11: Web V1 is gone).

FastAPI serves JSON and SSE only; every HTML document comes from Web V2
(Next.js), which sets its own headers in ``web/next.config.ts``. This module
still protects the API surface (JSON, streams, downloads) and any future
server-rendered response.

The CSP keeps ``'unsafe-inline'`` for the API's own JSON/error pages; it bans
plugins and framing and allows no third-party origin. Next's policy is the one
that governs the app shell.

HSTS is sent only when the client connection is HTTPS and not local. Browsers
ignore HSTS on plain HTTP, and pinning ``localhost`` breaks the default
``127.0.0.1`` bind. ``upgrade-insecure-requests`` is omitted for the same
reason: it would send the local API to HTTPS.
"""

from starlette.requests import Request

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "frame-src 'none'"
)

# 180 days. No includeSubDomains and no preload: this process often sits on a
# single host behind a reverse proxy, not on a registrable domain we control.
_HSTS_VALUE = "max-age=15552000"

_LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})


def client_sees_https(request: Request) -> bool:
    """True when the browser hop is HTTPS and not a local test client.

    Matches the session-cookie ``Secure`` rule: a reverse proxy signals TLS
    with ``X-Forwarded-Proto: https``. A spoofed header on a plain-HTTP
    response cannot pin HSTS, because browsers only honor the header when
    they received it over HTTPS.
    """
    client_host = request.client.host if request.client else ""
    if request.headers.get("x-forwarded-proto", "").lower() == "https":
        return True
    return request.url.scheme == "https" and client_host not in _LOCAL_CLIENTS


def security_headers(request: Request) -> dict[str, str]:
    """Headers applied to HTML, JSON, SSE, downloads and redirects."""
    headers = {
        "content-security-policy": CONTENT_SECURITY_POLICY,
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "no-referrer",
        "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    }
    if client_sees_https(request):
        headers["strict-transport-security"] = _HSTS_VALUE
    return headers


def apply_security_headers(response, request: Request):
    """Overwrite the policy headers on ``response`` and return it."""
    for name, value in security_headers(request).items():
        response.headers[name] = value
    return response
