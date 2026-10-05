"""Anti-SSRF guard: resolve DNS and block dangerous address ranges before connect.

Known limitation (accepted for the MVP): TOCTOU / DNS rebinding — the host could
resolve to a different address between this check and the actual connection.
The accepted mitigation is to call the guard immediately before every request
(including every redirect hop); there is no IP pinning at the transport layer.

Known limitation (accepted for the MVP): IPv6 translation prefixes that embed
IPv4 (NAT64 64:ff9b::/96, 6to4 2002::/16, Teredo 2001::/32) are not blocked —
abusing them requires a transition gateway on the auditor's own network, which
is out of the threat model. Only IPv4-mapped IPv6 (::ffff:/96) is unwrapped.
"""

import asyncio
import re
import socket
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from metatracer.core.exceptions import SecurityViolationError
from metatracer.core.logging import sanitize_for_log

_LOOPBACK_NETWORKS = (
    ip_network("127.0.0.0/8"),
    ip_network("::1/128"),
)

_OTHER_BLOCKED_NETWORKS = (
    ip_network("0.0.0.0/8"),  # unspecified / "this host on this network"
    ip_network("::/128"),  # unspecified IPv6
    ip_network("10.0.0.0/8"),  # RFC 1918
    ip_network("172.16.0.0/12"),  # RFC 1918
    ip_network("192.168.0.0/16"),  # RFC 1918
    ip_network("169.254.0.0/16"),  # link-local v4 (cloud metadata: 169.254.169.254)
    ip_network("fe80::/10"),  # link-local v6
    ip_network("100.64.0.0/10"),  # CGNAT
    ip_network("fc00::/7"),  # unique local IPv6
    ip_network("224.0.0.0/4"),  # multicast v4
    ip_network("ff00::/8"),  # multicast v6
    # TASK-32: documentation, benchmarking and reserved ranges (SSRF lists).
    ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ip_network("192.0.2.0/24"),  # TEST-NET-1
    ip_network("198.51.100.0/24"),  # TEST-NET-2
    ip_network("203.0.113.0/24"),  # TEST-NET-3
    ip_network("198.18.0.0/15"),  # benchmarking
    ip_network("240.0.0.0/4"),  # reserved (includes 255.255.255.255)
    ip_network("255.255.255.255/32"),
    ip_network("2001:db8::/32"),  # documentation
    ip_network("100::/64"),  # discard-only
)

# Dotted IPv4 whose labels are decimal, octal (leading 0) or hex (0x).
_IPV4_LABEL_RE = re.compile(r"(?:0x[0-9a-f]+|\d+)", re.IGNORECASE)


class NetworkSafetyGuard:
    """Blocks connections to loopback/private/reserved addresses (anti-SSRF).

    ``allow_loopback`` exempts ONLY the loopback ranges and exists so the test
    suite can run against a local mock server (METATRACER_ALLOW_LOOPBACK).
    Private, link-local, CGNAT, ULA and multicast ranges stay blocked even when
    ``allow_loopback`` is True.
    """

    def __init__(self, allow_loopback: bool = False) -> None:
        self._blocked = (
            _OTHER_BLOCKED_NETWORKS
            if allow_loopback
            else _LOOPBACK_NETWORKS + _OTHER_BLOCKED_NETWORKS
        )

    async def check(self, host: str, port: int = 443) -> None:
        """Resolve host and raise SecurityViolationError if any resolved IP is blocked.

        Must be called immediately before opening the connection. A host that
        cannot be resolved is refused: its addresses cannot be verified.
        Non-canonical IPv4 spellings (decimal dword, octal, hex) are refused
        before DNS: resolvers may map them onto loopback.
        """
        _reject_noncanonical_ipv4(host)
        addresses = await self._resolve(host, port)
        if not addresses:
            raise SecurityViolationError(
                f"refusing connection: no addresses resolved for {sanitize_for_log(host)}"
            )
        for address in addresses:
            self._check_address(address, host)

    async def _resolve(self, host: str, port: int) -> list[IPv4Address | IPv6Address]:
        literal = _parse_ip_literal(host)
        if literal is not None:
            return [literal]
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SecurityViolationError(
                f"refusing connection: cannot resolve {sanitize_for_log(host)}"
            ) from exc
        addresses: list[IPv4Address | IPv6Address] = []
        for info in infos:
            raw = str(info[4][0]).split("%", 1)[0]  # drop any IPv6 zone id
            try:
                addresses.append(ip_address(raw))
            except ValueError:
                continue  # unparseable entries are skipped, never trusted
        return addresses

    def _check_address(self, address: IPv4Address | IPv6Address, host: str) -> None:
        candidates = [address]
        if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
            # ::ffff:127.0.0.1 must not smuggle an IPv4 loopback past the guard.
            candidates.append(address.ipv4_mapped)
        for candidate in candidates:
            for network in self._blocked:
                if candidate in network:
                    raise SecurityViolationError(
                        f"refusing connection to blocked address {candidate} "
                        f"(host {sanitize_for_log(host)}, network {network})"
                    )


def _reject_noncanonical_ipv4(host: str) -> None:
    """Raise when ``host`` is an IPv4 written in a form ``ipaddress`` will not parse."""
    if _is_noncanonical_ipv4(host):
        raise SecurityViolationError(
            f"refusing connection: non-canonical IPv4 host {sanitize_for_log(host)}"
        )


def _is_noncanonical_ipv4(host: str) -> bool:
    text = host.strip().lower()
    if re.fullmatch(r"0x[0-9a-f]+", text):
        return True
    if re.fullmatch(r"\d+", text):
        try:
            value = int(text, 10)
        except ValueError:
            return False
        return 0 <= value <= 0xFFFFFFFF
    if "." not in text:
        return False
    labels = text.split(".")
    if not 2 <= len(labels) <= 4:
        return False
    if not all(_IPV4_LABEL_RE.fullmatch(label) for label in labels):
        return False
    # Short forms (``127.1``, ``10.1``) are not canonical dotted quads.
    if len(labels) != 4:
        return True
    for label in labels:
        if label.startswith("0x"):
            return True
        if len(label) > 1 and label.startswith("0"):
            return True
    return False


def _parse_ip_literal(host: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(host.split("%", 1)[0])
    except ValueError:
        return None
