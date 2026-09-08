"""HTTP response headers as structured metadata (TASK-09, subtask 9.2).

Only an allowlist of recon-relevant headers is persisted (namespace ``http``).
Authentication and cookie headers are dropped even if a server sent them —
they are secrets, not findings we want in SQLite or later LLM payloads.
"""

from collections.abc import Mapping

from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value

HTTP_NAMESPACE = "http"

# Recon-relevant response headers. Names match SafeHttpResponse (lower-cased).
HEADER_ALLOWLIST = frozenset(
    {
        "server",
        "x-powered-by",
        "x-aspnet-version",
        "x-aspnetmvc-version",
        "x-generator",
        "x-runtime",
        "x-version",
        "x-application-version",
        "via",
        "x-debug",
        "x-debug-token",
        "x-sourcemap",
        "sourcemap",
        "x-backend-server",
        "x-served-by",
        "x-redirect-by",
        "x-pingback",
    }
)

# Defense in depth: never persist these even if they slipped into the allowlist.
HEADER_DENYLIST = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "www-authenticate",
        "proxy-authenticate",
    }
)


def extract_http_headers(headers: Mapping[str, str]) -> list[ExtractedField]:
    """Return sanitized ``http`` fields for allowlisted response headers."""
    fields: list[ExtractedField] = []
    for raw_name, raw_value in headers.items():
        name = raw_name.strip().lower()
        if name in HEADER_DENYLIST or name not in HEADER_ALLOWLIST:
            continue
        value = sanitize_value(raw_value)
        if not value:
            continue
        fields.append(ExtractedField(namespace=HTTP_NAMESPACE, key=name, value=value))
    return fields
