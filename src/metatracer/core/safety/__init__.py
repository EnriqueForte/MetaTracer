"""Network safety core: scope validation, anti-SSRF guard and the single HTTP gateway."""

from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import (
    DEFAULT_MAX_FILE_BYTES,
    MAX_REDIRECT_HOPS,
    USER_AGENT,
    DomainRateLimiter,
    HttpTransportError,
    SafeHttpResponse,
    safe_httpx_request,
)
from metatracer.core.safety.scope import ScopeValidator, normalize_host

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "MAX_REDIRECT_HOPS",
    "USER_AGENT",
    "DomainRateLimiter",
    "HttpTransportError",
    "NetworkSafetyGuard",
    "SafeHttpResponse",
    "ScopeValidator",
    "normalize_host",
    "safe_httpx_request",
]
