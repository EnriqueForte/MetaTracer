"""Courtesy reading of ``robots.txt`` and the sitemaps it names.

``robots.txt`` never grants authorization. Scope stays the operator's
confirmed list, checked by ``ScopeValidator`` before any request. A
``Disallow`` is a courtesy omission: the URL is recorded and not requested.
An ``Allow``, including ``Allow: /``, does not add a host and does not
override scope.

A missing, oversized or unreadable file means "no courtesy rules", not "stop
the crawl" and not "the host is forbidden". ``Crawl-delay`` is ignored: the
run already has ``DomainRateLimiter``, and an unbounded delay would stall it.

The parser is deliberately small. It follows the common subset used by the
REP: groups of ``User-agent``, longest match wins, ``Allow`` wins a tie, ``*``
and ``$`` in a path. It does not merge a specific group with ``*``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from xml.etree import ElementTree

from metatracer.core.safety.http import USER_AGENT

# Bounded reads. A robots file or a sitemap past this is treated as unreadable
# rather than as a reason to keep downloading.
ROBOTS_MAX_BYTES = 512 * 1024
SITEMAP_MAX_BYTES = 512 * 1024
# One robots file can name a sitemap index that names the rest of the web.
# Two fetches and a hundred locations are enough to learn in-scope candidates
# without turning the crawl into a sitemap walk.
MAX_SITEMAP_FETCHES = 2
MAX_SITEMAP_LOCS = 100

_OMITTED = (
    "omitted by robots.txt Disallow; courtesy only, not an authorization decision"
)


def omission_message() -> str:
    """English text stored on the skipped asset. Stable for tests and the UI."""
    return _OMITTED


@dataclass(frozen=True, slots=True)
class RobotsPolicy:
    """Rules for one host, already reduced to the group that matches our agent.

    ``rules`` is ``(allow, path)`` in file order. An empty rule list allows
    every path. ``sitemaps`` are the ``Sitemap:`` URLs from the whole file,
    not only from our group: they are candidates, still subject to scope.
    """

    rules: tuple[tuple[bool, str], ...] = ()
    sitemaps: tuple[str, ...] = ()

    def allows(self, url: str) -> bool:
        """True when no matching ``Disallow`` is more specific than an ``Allow``."""
        target = _match_target(url)
        best_len = -1
        decision = True
        for allow, rule in self.rules:
            matched, length = _rule_matches(target, rule)
            if not matched:
                continue
            # Longer pattern wins. At equal length, Allow wins (REP).
            if length > best_len or (length == best_len and allow):
                best_len = length
                decision = allow
        return decision


def parse_robots(text: str, *, user_agent: str = USER_AGENT) -> RobotsPolicy:
    """Parse a robots body into the single group that applies to ``user_agent``.

    The product token in ``USER_AGENT`` (``MetaTracer``) beats ``*``. A group
    that names only another bot is ignored. ``Sitemap:`` lines are collected
    from the whole file.
    """
    sitemaps: list[str] = []
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    seen_rule = False

    def flush() -> None:
        nonlocal agents, rules, seen_rule
        if agents:
            groups.append((agents, rules))
        agents = []
        rules = []
        seen_rule = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "sitemap":
            if value:
                sitemaps.append(value)
            continue
        if field == "user-agent":
            if seen_rule:
                flush()
            if value:
                agents.append(value)
            continue
        if field not in ("allow", "disallow"):
            # Crawl-delay and unknown extensions are not rules.
            continue
        if not agents or not value:
            # An empty Disallow means "nothing in this directive", not "block all".
            continue
        seen_rule = True
        path = value if value.startswith(("/", "*")) else f"/{value}"
        rules.append((field == "allow", path))
    flush()
    return RobotsPolicy(rules=tuple(_select(groups, user_agent)), sitemaps=tuple(sitemaps))


def parse_sitemap(body: bytes) -> tuple[str, tuple[str, ...]]:
    """``("index"|"urlset", locations)``. Malformed XML yields an empty urlset.

    ``xml.etree`` does not resolve external entities, so a sitemap cannot
    pull a file into the process. Only ``loc`` text is kept.
    """
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ("urlset", ())
    kind = "index" if _local(root.tag) == "sitemapindex" else "urlset"
    locs = tuple(
        text
        for element in root.iter()
        if _local(element.tag) == "loc" and (text := (element.text or "").strip())
    )
    return kind, locs


def _select(
    groups: list[tuple[list[str], list[tuple[bool, str]]]], user_agent: str
) -> list[tuple[bool, str]]:
    """The most specific group for our agent, else ``*``, else no rules."""
    ua = user_agent.lower()
    best: list[tuple[bool, str]] | None = None
    best_len = -1
    star: list[tuple[bool, str]] | None = None
    for agents, rules in groups:
        for agent in agents:
            token = agent.strip().lower()
            if token == "*":
                if star is None:
                    star = rules
                continue
            if token and token in ua and len(token) > best_len:
                best = rules
                best_len = len(token)
    if best is not None:
        return best
    return star or []


def _match_target(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        return f"{path}?{parts.query}"
    return path


def _rule_matches(target: str, rule: str) -> tuple[bool, int]:
    """Whether ``rule`` matches ``target``, and the rule's specificity (its length)."""
    anchored = rule.endswith("$")
    body = rule[:-1] if anchored else rule
    specificity = len(rule)
    if "*" not in body:
        if anchored:
            return target == body, specificity
        return target.startswith(body), specificity
    pattern = "^" + ".*".join(re.escape(part) for part in body.split("*"))
    if anchored:
        pattern += "$"
    return re.match(pattern, target) is not None, specificity


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
