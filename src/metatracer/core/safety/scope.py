"""Scope validation: decide whether a host is covered by the confirmed scope.

Known limitation (accepted): there is no full Public Suffix List, so
``foo.co.uk`` is an opaque domain. Creating a scope of a known public suffix
(``co.uk`` and a short built-in list) is allowed and logged as a warning.
Single-label bases (``com``, ``*.com``) are rejected at scope creation.
"""

import logging
from collections.abc import Iterable
from ipaddress import ip_address

from metatracer.core.exceptions import OutOfScopeError
from metatracer.core.logging import sanitize_for_log

logger = logging.getLogger("metatracer.core.safety.scope")

# Not a Public Suffix List. Entries equal to one of these are warned about
# because they match every name underneath (TASK-32).
_KNOWN_PUBLIC_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.jp",
        "co.nz",
        "co.za",
        "co.kr",
        "co.in",
        "com.br",
        "com.mx",
        "com.tr",
        "com.cn",
        "com.tw",
        "com.ar",
        "com.sg",
        "com.hk",
    }
)

_WILDCARD_PREFIX = "*."


def normalize_host(value: str) -> str:
    """Reduce a URL or host-ish string to a normalized host name.

    Strips scheme, userinfo, port, path, query and fragment; lowercases;
    removes the trailing dot. Returns "" when nothing host-like remains.
    """
    host = value.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    elif host.startswith("//"):  # scheme-relative "//host/path"
        host = host[2:]
    # Path, query and fragment always come after the authority component.
    for separator in ("/", "?", "#"):
        host = host.split(separator, 1)[0]
    if "@" in host:  # userinfo (http://user@host): the host follows the last '@'
        host = host.rsplit("@", 1)[1]
    if host.startswith("["):  # bracketed IPv6 literal, optionally with :port
        closing = host.find("]")
        host = host[1:closing] if closing != -1 else host[1:]
    elif host.count(":") == 1:  # host:port — a bare IPv6 literal has several colons
        host = host.split(":", 1)[0]
    host = host.rstrip(".")
    return _to_idna(host)


def _to_idna(host: str) -> str:
    """Punycode the host the same way ``urlsplit().hostname`` does.

    IP literals are left unchanged. An unencodable name becomes "" so it
    matches nothing.
    """
    if not host or host.startswith("*."):
        base = host[2:] if host.startswith("*.") else host
        encoded = _idna_labels(base)
        if host.startswith("*."):
            return f"*.{encoded}" if encoded else ""
        return encoded
    return _idna_labels(host)


def _idna_labels(host: str) -> str:
    if not host:
        return ""
    try:
        ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def assert_registrable_scope(value: str) -> None:
    """Reject a one-label scope base and warn on a known public suffix.

    ``com`` and ``*.com`` match far more than an authorization covers.
    ``co.uk`` is still stored (there is no full PSL) but a warning is logged.
    """
    host = normalize_host(value)
    if not host:
        raise ValueError("scope entry is empty after normalization")
    base = host[2:] if host.startswith("*.") else host
    if "." not in base and ":" not in base:
        raise ValueError(
            f"scope '{value}' is a single label; name a domain such as 'target.com'"
        )
    if base in _KNOWN_PUBLIC_SUFFIXES:
        logger.warning(
            "scope %s is a known public suffix; it matches every name under it",
            sanitize_for_log(base),
        )


class ScopeValidator:
    """Decides whether hosts are inside the authorized scope.

    Matching rules (per entry after normalization):

    - plain ``target.com`` matches the apex and any subdomain
      (``host == domain`` or ``host.endswith("." + domain)``), so
      ``evil-target.com`` never matches ``target.com``;
    - wildcard ``*.target.com`` matches subdomains only, never the apex
      (list the apex explicitly as well if it is in scope).
    """

    def __init__(self, allowed_scope: Iterable[str]) -> None:
        self._exact: set[str] = set()
        self._wildcards: set[str] = set()
        for entry in allowed_scope:
            normalized = normalize_host(entry)
            if not normalized:
                continue
            if normalized.startswith(_WILDCARD_PREFIX):
                base = normalized[len(_WILDCARD_PREFIX) :]
                if base:
                    self._wildcards.add(base)
            else:
                self._exact.add(normalized)

    def is_in_scope(self, host_or_url: str) -> bool:
        """True when the normalized host is covered by the allowed scope."""
        host = normalize_host(host_or_url)
        if not host:
            return False
        if host in self._exact:
            return True
        if any(host.endswith("." + domain) for domain in self._exact):
            return True
        # The "." prefix in the suffix check is what excludes the apex itself.
        return any(host.endswith("." + base) for base in self._wildcards)

    def validate(self, host_or_url: str) -> str:
        """Return the normalized host if in scope; raise OutOfScopeError otherwise."""
        host = normalize_host(host_or_url)
        if not self.is_in_scope(host):
            raise OutOfScopeError(
                f"host outside the confirmed scope: {sanitize_for_log(host_or_url)}"
            )
        return host
