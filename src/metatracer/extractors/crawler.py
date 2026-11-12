"""Depth-1 discovery of public documents on in-scope pages (TASK-01 subtask 1.1.2).

This is a superficial crawl of a single page — not a web-scale bot: the entry
page plus the document references on it. Since TASK-09 that includes in-scope
``<script src>`` ending in ``.js``. No recursion and no authentication.
``robots.txt`` is not read here: ingestion consults it before a URL is
requested, and a ``Disallow`` never widens scope. Off-scope hosts and
non-HTTP schemes are discarded before they are ever requested.

References collected, all in-scope and sharing one cap:

- ``<a href>`` and ``<img src>`` (original contract);
- ``srcset`` on ``<img>`` and ``<source>`` — one URL per attribute, the
  candidate with the highest declared density or width, so a responsive image
  is not downloaded three times;
- ``<meta property="og:image">`` and ``<meta name="twitter:image">``.
- ``url()`` inside in-scope stylesheets (the CSS body is not persisted).

A URL whose path ends in a known document or script extension is queued
directly. A URL with no such extension (``/download?id=7``, a CDN path) is
returned in ``probe_urls``: ingestion issues a HEAD and only GETs when the
declared type can be a document. ``robots.txt`` is applied by ingestion,
not by this crawler.

The fetched HTML is returned to the caller so ingestion can persist the page
as an asset without a second GET.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from metatracer.core.exceptions import MetaTracerError, ScopeNotConfirmedError
from metatracer.core.logging import sanitize_for_log
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import (
    DomainRateLimiter,
    HttpTransportError,
    safe_httpx_request,
)
from metatracer.core.safety.scope import ScopeValidator
from metatracer.extractors.targets import DOCUMENT_EXTENSIONS, SCRIPT_EXTENSIONS

logger = logging.getLogger("metatracer.extractors.crawler")


def reference_kind(url: str) -> str | None:
    """How a URL found outside HTML (a sitemap ``loc``) should be queued.

    Same classification as an HTML reference: document, script, page, probe,
    or ``None`` when the path is never fetched.
    """
    return _reference_kind(urlsplit(url).path or "/")


def _reference_kind(path: str) -> str | None:
    """``document``, ``script``, ``probe``, or ``None`` when the path is never a document.

    Extensionless paths (and paths whose type is only a query string) are
    ``probe``: ingestion confirms the declared type with HEAD before GET.
    """
    lowered = path.lower()
    if lowered.endswith(DOCUMENT_EXTENSIONS):
        return "document"
    if lowered.endswith(SCRIPT_EXTENSIONS):
        return "script"
    # HTML links are the next crawl hop, not documents. Depth decides whether
    # ingestion fetches them; they are never parsed as a PDF or an image.
    if lowered.endswith((".html", ".htm")):
        return "page"
    if lowered.endswith(_NEVER_DOCUMENT_SUFFIXES):
        return None
    return "probe"


def _srcset_score(descriptor: str) -> float:
    """Numeric rank of a srcset descriptor. ``2x`` and ``800w`` compare within one attribute."""
    text = descriptor.strip().lower()
    if not text:
        return 1.0
    try:
        if text.endswith("x"):
            return float(text[:-1])
        if text.endswith("w"):
            return float(text[:-1])
    except ValueError:
        return 1.0
    return 1.0


def _best_srcset(raw: object) -> str | None:
    """The single URL in a ``srcset`` with the highest declared density or width.

    One attribute yields one download. A responsive image that lists three
    widths is not three assets.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    best_url: str | None = None
    best_score = -1.0
    for part in raw.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        score = _srcset_score(bits[1] if len(bits) > 1 else "")
        if score > best_score:
            best_score = score
            best_url = bits[0]
    return best_url


def _sniff_html(body: bytes) -> bool:
    """True when an empty Content-Type still looks like an HTML document."""
    head = body.lstrip()[:64].lower()
    return head.startswith((b"<!doctype", b"<html"))


MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MB page ceiling (subtask 1.1.2)
MAX_CSS_BYTES = 512 * 1024
MAX_STYLESHEETS_PER_PAGE = 8
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.IGNORECASE)
_SKIPPED_SCHEMES = ("javascript:", "data:", "mailto:", "tel:")
_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
# Paths that are never documents. Dropped before a HEAD: an ``.html`` link is
# another page (not crawled — depth stays 1) and the rest have no extractor.
_NEVER_DOCUMENT_SUFFIXES = (
    ".css",
    ".json",
    ".xml",
    ".ico",
    ".map",
    ".woff",
    ".woff2",
    ".txt",
)
# Social/document meta the crawler treats as a reference, not as page metadata.
_IMAGE_META = frozenset(
    {
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
    }
)


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """One crawled HTML page plus the child URLs discovered on it.

    ``discovery_truncated`` is True when the per-page asset cap stopped the
    link scan before it reached the end of the document. Without this flag a
    page that yielded exactly ``max_assets`` children is indistinguishable from
    a page that had more links: the run would report a complete crawl that
    never looked at the rest of the page.
    """

    source_url: str
    url: str  # final URL after in-scope redirects
    headers: dict[str, str]
    content: bytes
    content_type: str
    document_urls: list[str]
    script_urls: list[str]
    # In-scope URLs with no document/script extension. Ingestion HEADs these
    # and GETs only when the declared type can be a supported document.
    probe_urls: list[str] = field(default_factory=list)
    # In-scope ``.html`` / ``.htm`` links. Ingestion follows them only while
    # ``budget.depth`` still allows another hop; they do not consume the
    # per-page asset cap (that cap is for documents, not for the crawl frontier).
    page_urls: list[str] = field(default_factory=list)
    discovery_truncated: bool = False

    @property
    def child_urls(self) -> list[str]:
        """Typed document then script URLs, already capped and de-duplicated.

        Probe URLs are not included: they are not yet known to be documents.
        """
        return [*self.document_urls, *self.script_urls]


class PublicDocCrawler:
    """Finds document URLs linked directly from one in-scope page."""

    def __init__(
        self,
        *,
        scope: ScopeValidator,
        guard: NetworkSafetyGuard,
        rate_limiter: DomainRateLimiter,
        max_html_bytes: int = MAX_HTML_BYTES,
    ) -> None:
        self._scope = scope
        self._guard = guard
        self._rate_limiter = rate_limiter
        self._max_html_bytes = max_html_bytes

    async def discover(
        self,
        page_url: str,
        *,
        scope_confirmed: bool,
        max_assets: int,
        download_semaphore: asyncio.Semaphore | None = None,
    ) -> list[str]:
        """Return up to ``max_assets`` absolute document URLs linked from the page.

        Script URLs are omitted here so existing TASK-01 callers keep their
        document-only contract. Ingestion uses :meth:`fetch_page`.
        """
        page = await self.fetch_page(
            page_url,
            scope_confirmed=scope_confirmed,
            max_assets=max_assets,
            download_semaphore=download_semaphore,
        )
        return page.document_urls if page is not None else []

    async def fetch_page(
        self,
        page_url: str,
        *,
        scope_confirmed: bool,
        max_assets: int,
        download_semaphore: asyncio.Semaphore | None = None,
    ) -> FetchedPage | None:
        """Fetch one HTML page and collect in-scope document + script URLs.

        A page that cannot be fetched or is not HTML yields ``None`` — a
        failed page never aborts the run. ScopeNotConfirmedError propagates:
        it is a contract violation, not a per-page failure.
        """
        try:
            response = await safe_httpx_request(
                page_url,
                scope=self._scope,
                guard=self._guard,
                scope_confirmed=scope_confirmed,
                rate_limiter=self._rate_limiter,
                max_file_bytes=self._max_html_bytes,
                download_semaphore=download_semaphore,
            )
        except ScopeNotConfirmedError:
            raise
        except (MetaTracerError, HttpTransportError) as exc:
            # RedirectOutOfScopeError, SecurityViolationError and httpx transport
            # errors all mean 'this page could not be crawled'; the run continues.
            logger.warning(
                "page not crawled: %s (%s)",
                sanitize_for_log(page_url),
                sanitize_for_log(type(exc).__name__),
            )
            return None
        if response.too_large:
            logger.info(
                "page exceeds the HTML ceiling (%d bytes), not crawled: %s",
                self._max_html_bytes,
                sanitize_for_log(page_url),
            )
            return None
        if response.status_code != 200:
            logger.info(
                "page returned HTTP %d, not crawled: %s",
                response.status_code,
                sanitize_for_log(page_url),
            )
            return None
        content_type = (response.content_type or "").split(";", 1)[0].strip().lower()
        if not content_type:
            if not _sniff_html(response.content):
                logger.info(
                    "page has an empty content type and does not look like HTML, not crawled: %s",
                    sanitize_for_log(page_url),
                )
                return None
            content_type = "text/html"
        elif not content_type.startswith(_HTML_CONTENT_TYPES):
            logger.info(
                "page is not HTML (%s), not crawled: %s",
                sanitize_for_log(content_type),
                sanitize_for_log(page_url),
            )
            return None
        documents, scripts, probes, pages, truncated = self._extract_child_urls(
            response.content, response.url, max_assets
        )
        css_docs, css_truncated = await self._harvest_css_urls(
            response.content,
            response.url,
            max_assets,
            already=len(documents) + len(scripts) + len(probes),
            seen=set(documents + scripts + probes + pages),
            scope_confirmed=scope_confirmed,
            download_semaphore=download_semaphore,
        )
        if css_docs:
            documents.extend(css_docs)
        truncated = truncated or css_truncated
        return FetchedPage(
            source_url=page_url,
            url=response.url,
            headers=dict(response.headers),
            content=response.content,
            content_type=content_type or "text/html",
            document_urls=documents,
            script_urls=scripts,
            probe_urls=probes,
            page_urls=pages,
            discovery_truncated=truncated,
        )

    def _extract_child_urls(
        self, html: bytes, final_url: str, max_assets: int
    ) -> tuple[list[str], list[str], list[str], list[str], bool]:
        """Collect in-scope references, sharing one cap across documents.

        Returns ``(documents, scripts, probes, pages, truncated)``. ``pages``
        are HTML links and do not consume the asset cap. ``truncated`` is True
        when a document reference was abandoned because the cap was full.
        """
        soup = BeautifulSoup(html, "html.parser")
        documents: list[str] = []
        scripts: list[str] = []
        probes: list[str] = []
        pages: list[str] = []
        seen: set[str] = set()
        state = {"truncated": False}
        buckets = {"document": documents, "script": scripts, "probe": probes, "page": pages}

        def _full() -> bool:
            return len(documents) + len(scripts) + len(probes) >= max_assets

        def _consider(raw: object) -> None:
            if not raw or not isinstance(raw, str):
                return
            candidate = raw.strip()
            if not candidate or candidate.lower().startswith(_SKIPPED_SCHEMES):
                return
            absolute = urljoin(final_url, candidate)
            parsed = urlsplit(absolute)
            if parsed.scheme.lower() not in ("http", "https"):
                return
            if not self._scope.is_in_scope(absolute):
                logger.debug("discarding off-scope link: %s", sanitize_for_log(absolute))
                return
            # Fragments do not identify a different resource.
            absolute = parsed._replace(fragment="").geturl()
            kind = _reference_kind(parsed.path)
            if kind is None or absolute in seen:
                return
            # HTML links are the crawl frontier, not downloads, so they must
            # not push a real document out of the asset cap.
            if kind != "page" and _full():
                state["truncated"] = True
                return
            seen.add(absolute)
            buckets[kind].append(absolute)

        for tag in soup.find_all("a"):
            _consider(tag.get("href"))
        for tag in soup.find_all("img"):
            _consider(tag.get("src"))
            _consider(_best_srcset(tag.get("srcset")))
        for tag in soup.find_all("source"):
            _consider(tag.get("src"))
            _consider(_best_srcset(tag.get("srcset")))
        for tag in soup.find_all("meta"):
            name = tag.get("property") or tag.get("name") or ""
            if isinstance(name, str) and name.strip().lower() in _IMAGE_META:
                _consider(tag.get("content"))
        for tag in soup.find_all("script"):
            _consider(tag.get("src"))
        if state["truncated"]:
            logger.info("asset discovery cap reached (%d); links dropped", max_assets)
        return documents, scripts, probes, pages, state["truncated"]

    def _stylesheet_urls(self, html: bytes, final_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for tag in soup.find_all("link"):
            if not _is_stylesheet(tag):
                continue
            raw = tag.get("href")
            if not raw or not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if not candidate or candidate.lower().startswith(_SKIPPED_SCHEMES):
                continue
            absolute = urljoin(final_url, candidate)
            parsed = urlsplit(absolute)
            if parsed.scheme.lower() not in ("http", "https"):
                continue
            if not self._scope.is_in_scope(absolute):
                continue
            absolute = parsed._replace(fragment="").geturl()
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
            if len(urls) >= MAX_STYLESHEETS_PER_PAGE:
                break
        return urls

    async def _harvest_css_urls(
        self,
        html: bytes,
        final_url: str,
        max_assets: int,
        *,
        already: int,
        seen: set[str],
        scope_confirmed: bool,
        download_semaphore: asyncio.Semaphore | None,
    ) -> tuple[list[str], bool]:
        """Fetch in-scope stylesheets and enqueue allowlisted ``url()`` documents.

        The CSS bytes are never persisted as an asset.
        """
        documents: list[str] = []
        truncated = False
        if already >= max_assets:
            return documents, True
        for css_url in self._stylesheet_urls(html, final_url):
            try:
                response = await safe_httpx_request(
                    css_url,
                    scope=self._scope,
                    guard=self._guard,
                    scope_confirmed=scope_confirmed,
                    rate_limiter=self._rate_limiter,
                    max_file_bytes=MAX_CSS_BYTES,
                    download_semaphore=download_semaphore,
                )
            except ScopeNotConfirmedError:
                raise
            except (MetaTracerError, HttpTransportError) as exc:
                logger.info(
                    "stylesheet not read: %s (%s)",
                    sanitize_for_log(css_url),
                    sanitize_for_log(type(exc).__name__),
                )
                continue
            if response.too_large or response.status_code != 200 or not response.content:
                continue
            for raw in _css_url_values(response.content):
                if raw.lower().startswith(_SKIPPED_SCHEMES):
                    continue
                absolute = urljoin(css_url, raw.strip())
                parsed = urlsplit(absolute)
                if parsed.scheme.lower() not in ("http", "https"):
                    continue
                if not self._scope.is_in_scope(absolute):
                    continue
                absolute = parsed._replace(fragment="").geturl()
                if _reference_kind(parsed.path) != "document" or absolute in seen:
                    continue
                if already + len(documents) >= max_assets:
                    truncated = True
                    return documents, truncated
                seen.add(absolute)
                documents.append(absolute)
        return documents, truncated


def _is_stylesheet(tag: object) -> bool:
    rel = getattr(tag, "get", lambda _key: None)("rel")
    if rel is None:
        return False
    values = rel if isinstance(rel, list) else str(rel).split()
    return any(str(item).lower() == "stylesheet" for item in values)


def _css_url_values(body: bytes) -> list[str]:
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return []
    return [match.group(2).strip() for match in _CSS_URL_RE.finditer(text)]
