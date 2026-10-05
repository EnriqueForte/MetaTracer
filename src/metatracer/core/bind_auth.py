"""Refuse to listen on a public interface while authentication is off (TASK-27).

``metatracer serve`` on loopback keeps the TASK-24 localhost-first default
(auth optional). Docker publishes ``0.0.0.0``, so the same default would
expose scans, webhook creation and knowledge import to the network. A
non-loopback bind with ``METATRACER_AUTH_ENABLED=false`` exits before the
socket opens.

``METATRACER_ALLOW_UNAUTHENTICATED_BIND=true`` is an explicit, noisy escape.
It does not touch scope validation or ``NetworkSafetyGuard``.
"""

from __future__ import annotations

import ipaddress
import logging
import sys

from metatracer.core.config import Settings
from metatracer.core.exceptions import UnauthenticatedPublicBindError
from metatracer.core.logging import configure_logging, sanitize_for_log

logger = logging.getLogger("metatracer.core.bind_auth")

_LOCALHOST_NAMES = frozenset({"localhost", "localhost."})


def is_loopback_bind(host: str) -> bool:
    """True for loopback IPs and the name ``localhost`` (not ``0.0.0.0`` or ``::``)."""
    text = host.strip().lower()
    if text in _LOCALHOST_NAMES:
        return True
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.split("%", 1)[0]
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def enforce_public_bind_auth(settings: Settings, bind_host: str | None = None) -> None:
    """Raise if ``bind_host`` is public and auth is off without the escape hatch.

    ``bind_host`` defaults to ``settings.bind_host`` (the Docker entrypoint).
    The CLI passes the resolved ``--host`` so a flag cannot bypass the check.
    """
    host = bind_host if bind_host is not None else settings.bind_host
    if is_loopback_bind(host) or settings.auth_enabled:
        return
    safe_host = sanitize_for_log(host)
    if settings.allow_unauthenticated_bind:
        logger.warning(
            "METATRACER_ALLOW_UNAUTHENTICATED_BIND is set: listening on %s "
            "with authentication disabled. Scope checks and the network safety "
            "guard stay in force.",
            safe_host,
        )
        return
    raise UnauthenticatedPublicBindError(
        f"refusing to bind {safe_host}: authentication is disabled. "
        "Set METATRACER_AUTH_ENABLED=true, bind a loopback address "
        "(127.0.0.1, ::1 or localhost), or set "
        "METATRACER_ALLOW_UNAUTHENTICATED_BIND=true to start anyway. "
        "That override is logged as a warning and does not disable scope "
        "or network safety checks."
    )


def enforce_public_bind_from_env() -> None:
    """Docker ``web`` entrypoint: exit 1 instead of opening a public socket."""
    settings = Settings()
    configure_logging(settings.log_level)
    try:
        enforce_public_bind_auth(settings)
    except UnauthenticatedPublicBindError as exc:
        logger.error("%s", sanitize_for_log(exc, max_length=500))
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc
