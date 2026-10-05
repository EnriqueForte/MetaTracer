"""Depth-1 discovery of public documents on in-scope pages (TASK-01 subtask 1.1.2).

This is a superficial crawl of a single page — not a web-scale bot: the entry
page plus direct document links (``<a href>``, ``<img src>``) and, since
TASK-09, in-scope ``<script src>`` ending in ``.js``. No recursion, no
authentication, no robots.txt machinery (documented MVP simplification:
one-page crawl, conservative rate limit inherited from the HTTP gateway).
Off-scope hosts and non-HTTP schemes are discarded before they are ever
requested.

The fetched HTML is returned to the caller so ingestion can persist the page
as an asset without a second GET.
"""

import asyncio
import logging
from dataclasses import dataclass
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


def _sniff_html(body: bytes) -> bool:
    """True when an empty Content-Type still looks like an HTML document."""
    head = body.lstrip()[:64].lower()
    return head.startswith((b"<!doctype", b"<html"))


MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MB page ceiling (subtask 1.1.2)
_SKIPPED_SCHEMES = ("javascript:", "data:", "mailto:", "tel:")
_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """One crawled HTML page plus the child URLs discovered on it."""

    source_url: str
    url: str  # final URL after in-scope redirects
    headers: dict[str, str]
    content: bytes
    content_type: str
    document_urls: list[str]
    script_urls: list[str]

    @property
    def child_urls(self) -> list[str]:
        """Document then script URLs, already capped and de-duplicated."""
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
        documents, scripts = self._extract_child_urls(
            response.content, response.url, max_assets
        )
        return FetchedPage(
            source_url=page_url,
            url=response.url,
            headers=dict(response.headers),
            content=response.content,
            content_type=content_type or "text/html",
            document_urls=documents,
            script_urls=scripts,
        )

    def _extract_child_urls(
        self, html: bytes, final_url: str, max_assets: int
    ) -> tuple[list[str], list[str]]:
        """Collect in-scope document and script URLs, sharing one cap."""
        soup = BeautifulSoup(html, "html.parser")
        documents: list[str] = []
        scripts: list[str] = []
        seen: set[str] = set()

        def _consider(raw: object, extensions: tuple[str, ...], bucket: list[str]) -> None:
            if len(documents) + len(scripts) >= max_assets:
                return
            if not raw or not isinstance(raw, str):
                return
            candidate = raw.strip()
            if not candidate or candidate.lower().startswith(_SKIPPED_SCHEMES):
                return
            absolute = urljoin(final_url, candidate)
            scheme = urlsplit(absolute).scheme.lower()
            if scheme not in ("http", "https"):
                return
            if not self._scope.is_in_scope(absolute):
                logger.debug("discarding off-scope link: %s", sanitize_for_log(absolute))
                return
            if not urlsplit(absolute).path.lower().endswith(extensions):
                return
            if absolute in seen:
                return
            seen.add(absolute)
            bucket.append(absolute)

        for tag in soup.find_all(["a", "img"]):
            if len(documents) + len(scripts) >= max_assets:
                logger.info("asset discovery cap reached (%d); links dropped", max_assets)
                break
            _consider(
                tag.get("href" if tag.name == "a" else "src"),
                DOCUMENT_EXTENSIONS,
                documents,
            )
        for tag in soup.find_all("script"):
            if len(documents) + len(scripts) >= max_assets:
                logger.info("asset discovery cap reached (%d); links dropped", max_assets)
                break
            _consider(tag.get("src"), SCRIPT_EXTENSIONS, scripts)
        return documents, scripts
