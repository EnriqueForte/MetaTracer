"""PublicDocCrawler: link extraction, scope filtering, caps (TASK-01 subtask 1.1.2).

The HTML fixture carries in-scope absolute/relative links, an off-scope host,
non-HTTP schemes, a non-document link and a duplicate. DNS and transport are
faked; ScopeValidator and NetworkSafetyGuard are the real ones.
"""

from collections.abc import Callable
from pathlib import Path

import httpx

from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import DomainRateLimiter
from metatracer.core.safety.scope import ScopeValidator
from metatracer.extractors.crawler import PublicDocCrawler

FIXTURE_HTML = (Path(__file__).parent.parent / "fixtures" / "page.html").read_bytes()


def _crawler(scope: tuple[str, ...] = ("target.com",)) -> PublicDocCrawler:
    return PublicDocCrawler(
        scope=ScopeValidator(scope),
        guard=NetworkSafetyGuard(allow_loopback=False),
        rate_limiter=DomainRateLimiter(1000.0),  # fast; throttling has its own test
    )


def _html_handler(
    body: bytes = FIXTURE_HTML, content_type: str = "text/html"
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-type": content_type})
        return httpx.Response(200, headers={"content-type": content_type}, content=body)

    return handler


async def test_discovers_in_scope_documents(fake_public_dns, install_transport) -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        assert request.url.host == "target.com"  # off-scope hosts must never be hit
        return _html_handler()(request)

    install_transport(handler)
    urls = await _crawler().discover("http://target.com/page", scope_confirmed=True, max_assets=50)
    assert urls == [
        "http://target.com/docs/report.pdf",  # relative, resolved against the page
        "https://target.com/img/photo.jpg",  # absolute in-scope
        "http://target.com/images/pic.png",  # <img src>
        "https://sub.target.com/pic.webp",  # subdomain of a scope entry
    ]
    # The off-scope link, javascript:/data:/mailto: and the .html page link were
    # discarded, the duplicate collapsed — and nothing but the page was requested.
    assert set(requested_hosts) == {"target.com"}


async def test_relative_links_resolve_against_final_url(fake_public_dns, install_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final/page"})
        if request.url.path == "/final/page":
            return _html_handler(b'<a href="doc.pdf">d</a>')(request)
        raise AssertionError(f"unexpected request: {request.url}")

    install_transport(handler)
    urls = await _crawler().discover("http://target.com/start", scope_confirmed=True, max_assets=50)
    assert urls == ["http://target.com/final/doc.pdf"]


async def test_html_over_ceiling_is_not_crawled(fake_public_dns, install_transport) -> None:
    get_requested = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_requested
        if request.method == "GET":
            get_requested = True
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": str(6 * 1024 * 1024)},
        )

    install_transport(handler)
    urls = await _crawler().discover("http://target.com/huge", scope_confirmed=True, max_assets=50)
    assert urls == []
    assert get_requested is False  # the HEAD-declared size was enough to bail out


async def test_non_html_page_is_not_crawled(fake_public_dns, install_transport) -> None:
    install_transport(_html_handler(content_type="application/pdf"))
    urls = await _crawler().discover(
        "http://target.com/download", scope_confirmed=True, max_assets=50
    )
    assert urls == []


async def test_404_page_yields_nothing(fake_public_dns, install_transport) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    install_transport(handler)
    urls = await _crawler().discover("http://target.com/gone", scope_confirmed=True, max_assets=50)
    assert urls == []


async def test_max_assets_cap_stops_enqueueing(fake_public_dns, install_transport) -> None:
    body = b"".join(f'<a href="/doc{i}.pdf">d{i}</a>'.encode() for i in range(5))
    install_transport(_html_handler(body))
    urls = await _crawler().discover("http://target.com/page", scope_confirmed=True, max_assets=2)
    assert urls == ["http://target.com/doc0.pdf", "http://target.com/doc1.pdf"]


async def test_script_src_in_scope_is_discovered(fake_public_dns, install_transport) -> None:
    body = (
        b'<html><body>'
        b'<a href="/doc.pdf">d</a>'
        b'<script src="/static/app.js"></script>'
        b'<script src="https://evil.com/steal.js"></script>'
        b"</body></html>"
    )
    install_transport(_html_handler(body))
    page = await _crawler().fetch_page(
        "http://target.com/page", scope_confirmed=True, max_assets=50
    )
    assert page is not None
    assert page.document_urls == ["http://target.com/doc.pdf"]
    assert page.script_urls == ["http://target.com/static/app.js"]
    assert page.child_urls == [
        "http://target.com/doc.pdf",
        "http://target.com/static/app.js",
    ]


async def test_discover_stays_document_only(fake_public_dns, install_transport) -> None:
    body = b'<html><body><a href="/doc.pdf">d</a><script src="/app.js"></script></body></html>'
    install_transport(_html_handler(body))
    urls = await _crawler().discover("http://target.com/page", scope_confirmed=True, max_assets=50)
    assert urls == ["http://target.com/doc.pdf"]
