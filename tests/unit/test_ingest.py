"""IngestionPipeline end-to-end over a mocked transport (TASK-01 DoD).

Covers: pdfinfo/EXIF persistence linked to the asset, domain crawl with
rate-limited discovery, per-asset failure isolation, redirect-out-of-scope,
magic-byte allowlist, duplicate hashes, the global asset cap, temp-file
cleanup and the scope-confirmation gate. DNS and transport are faked;
ScopeValidator and NetworkSafetyGuard are the real ones.
"""

import json
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import ScopeNotConfirmedError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import ExtractionStatus, Run, SkipReason
from metatracer.db.repositories import AssetRepository, RawMetadataRepository, RunRepository
from metatracer.extractors.budget import BudgetTracker
from metatracer.extractors.ingest import IngestionPipeline
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

PDF_BYTES = make_pdf_bytes()
JPEG_BYTES = make_jpeg_bytes()

RouteMap = dict[str, tuple[int, str, bytes]]


def _settings(**overrides) -> Settings:
    defaults = {
        "max_assets_per_run": 50,
        "max_file_bytes": 50 * 1024 * 1024,
        "rate_limit_rps": 1000.0,  # fast tests; throttling has its own test
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/ingest-test.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _make_run(
    factory: async_sessionmaker[AsyncSession],
    targets: list[str],
    *,
    confirmed: bool = True,
) -> str:
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps(targets),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=confirmed,
            )
        )
        return run.id


def _routes(routes: RouteMap) -> Callable[[httpx.Request], httpx.Response]:
    """Serve (status, content_type, body) per path; HEAD gets headers only."""

    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(request.url.path)
        if route is None:
            return httpx.Response(404)
        status, content_type, body = route
        headers = {"content-type": content_type, "content-length": str(len(body))}
        if request.method == "HEAD":
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, headers=headers, content=body)

    return handler


async def _assets(factory, run_id: str):
    async with factory() as session:
        return await AssetRepository(session).list_by_run(run_id)


async def test_pdf_asset_metadata_persisted(
    session_factory, fake_public_dns, install_transport
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    run_id = await _make_run(session_factory, ["http://target.com/doc.pdf"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 1
    assets = await _assets(session_factory, run_id)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.extraction_status is ExtractionStatus.ok
    assert asset.content_type == "application/pdf"
    assert asset.file_size_bytes == len(PDF_BYTES)
    assert len(asset.file_hash_sha256) == 64

    async with session_factory() as session:
        items = await RawMetadataRepository(session).list_by_asset(asset.id)
        run = await RunRepository(session).get(run_id)
    by_key = {(item.namespace, item.key): item.value for item in items}
    assert by_key[("pdfinfo", "Author")] == "Jane Doe"
    assert by_key[("pdfinfo", "Producer")] == "Apache FOP 2.4"
    assert by_key[("xmp", "xmp:CreatorTool")] == "UnitTest Studio 9.1"
    assert run is not None and run.total_assets == 1


async def test_jpeg_gps_persisted_raw(session_factory, fake_public_dns, install_transport) -> None:
    install_transport(_routes({"/photo.jpg": (200, "image/jpeg", JPEG_BYTES)}))
    run_id = await _make_run(session_factory, ["http://target.com/photo.jpg"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 1
    assets = await _assets(session_factory, run_id)
    async with session_factory() as session:
        items = await RawMetadataRepository(session).list_by_asset(assets[0].id)
    by_key = {(item.namespace, item.key): item.value for item in items}
    assert by_key[("exif", "GPSLatitudeRef")] == "N"
    assert by_key[("exif", "GPSLatitude")] == '["40/1", "24/1", "4635/100"]'
    latitude = next(item for item in items if item.key == "GPSLatitude")
    assert latitude.value_normalized == "40.412875"
    assert latitude.normalized_kind == "decimal_degrees"


async def test_bare_domain_is_crawled_and_documents_discovered(
    session_factory, fake_public_dns, install_transport
) -> None:
    html = b'<html><body><a href="/a.pdf">a</a><img src="/p.jpg"></body></html>'
    install_transport(
        _routes(
            {
                "/": (200, "text/html", html),
                "/a.pdf": (200, "application/pdf", PDF_BYTES),
                "/p.jpg": (200, "image/jpeg", JPEG_BYTES),
            }
        )
    )
    run_id = await _make_run(session_factory, ["target.com"])  # bare domain, no scheme
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.pages_crawled == 1
    assert summary.documents_discovered == 2
    assert summary.assets_ok == 3  # crawled HTML page + two documents
    urls = {asset.source_url for asset in await _assets(session_factory, run_id)}
    assert urls == {
        "https://target.com/",
        "https://target.com/a.pdf",
        "https://target.com/p.jpg",
    }


async def test_html_page_and_js_and_headers_persisted(
    session_factory, fake_public_dns, install_transport
) -> None:
    html = (
        b"<!doctype html><html><head><title>Home</title>"
        b'<meta name="generator" content="WordPress 6.4.2"></head>'
        b'<body><!-- TODO: strip --><script src="/app.js"></script></body></html>'
    )
    js = b"/* FIXME: leftover */\nfunction boot() { return 1; }\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/", ""):
            headers = {
                "content-type": "text/html",
                "content-length": str(len(html)),
                "server": "nginx/1.18.0",
                "set-cookie": "session=secret",
            }
            if request.method == "HEAD":
                return httpx.Response(200, headers=headers)
            return httpx.Response(200, headers=headers, content=html)
        if request.url.path == "/app.js":
            headers = {
                "content-type": "application/javascript",
                "content-length": str(len(js)),
            }
            if request.method == "HEAD":
                return httpx.Response(200, headers=headers)
            return httpx.Response(200, headers=headers, content=js)
        return httpx.Response(404)

    install_transport(handler)
    run_id = await _make_run(session_factory, ["http://target.com/"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 2
    assets = await _assets(session_factory, run_id)
    by_url = {asset.source_url: asset for asset in assets}
    page = by_url["http://target.com/"]
    script = by_url["http://target.com/app.js"]
    assert page.extraction_status is ExtractionStatus.ok
    assert script.extraction_status is ExtractionStatus.ok

    async with session_factory() as session:
        page_items = await RawMetadataRepository(session).list_by_asset(page.id)
        js_items = await RawMetadataRepository(session).list_by_asset(script.id)
    page_keys = {(item.namespace, item.key): item.value for item in page_items}
    assert page_keys[("html", "title")] == "Home"
    assert page_keys[("html", "meta:generator")] == "WordPress 6.4.2"
    assert page_keys[("html", "comment")] == "TODO: strip"
    assert page_keys[("http", "server")] == "nginx/1.18.0"
    assert all(item.key != "set-cookie" for item in page_items)
    assert all("secret" not in item.value for item in page_items)
    assert any(item.namespace == "js" and "FIXME" in item.value for item in js_items)


async def test_js_404_does_not_abort_run(
    session_factory, fake_public_dns, install_transport
) -> None:
    html = b'<html><body><script src="/missing.js"></script></body></html>'
    install_transport(
        _routes(
            {
                "/": (200, "text/html", html),
                "/missing.js": (404, "text/plain", b"gone"),
            }
        )
    )
    run_id = await _make_run(session_factory, ["http://target.com/"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert summary.assets_ok == 1  # the HTML page
    assert summary.assets_failed == 1
    by_url = {asset.source_url: asset for asset in await _assets(session_factory, run_id)}
    assert by_url["http://target.com/missing.js"].extraction_status is ExtractionStatus.failed


async def test_failures_do_not_stop_the_run(
    session_factory, fake_public_dns, install_transport
) -> None:
    install_transport(
        _routes(
            {
                "/missing.pdf": (404, "text/html", b"not found"),
                "/broken.pdf": (200, "application/pdf", b"%PDF-1.4\nbroken body\n"),
                "/doc.pdf": (200, "application/pdf", PDF_BYTES),
            }
        )
    )
    run_id = await _make_run(
        session_factory,
        [
            "http://target.com/missing.pdf",
            "http://target.com/broken.pdf",
            "http://target.com/doc.pdf",
        ],
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert (summary.assets_ok, summary.assets_failed) == (1, 2)
    by_url = {a.source_url: a for a in await _assets(session_factory, run_id)}
    missing = by_url["http://target.com/missing.pdf"]
    assert missing.extraction_status is ExtractionStatus.failed
    assert "404" in (missing.error_message or "")
    broken = by_url["http://target.com/broken.pdf"]
    assert broken.extraction_status is ExtractionStatus.failed
    assert broken.skip_reason is None
    assert by_url["http://target.com/doc.pdf"].extraction_status is ExtractionStatus.ok


async def test_duplicate_hash_is_skipped_but_traced(
    session_factory, fake_public_dns, install_transport
) -> None:
    install_transport(
        _routes(
            {
                "/dup1.pdf": (200, "application/pdf", PDF_BYTES),
                "/dup2.pdf": (200, "application/pdf", PDF_BYTES),
            }
        )
    )
    run_id = await _make_run(
        session_factory, ["http://target.com/dup1.pdf", "http://target.com/dup2.pdf"]
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert (summary.assets_ok, summary.assets_skipped) == (1, 1)
    by_url = {a.source_url: a for a in await _assets(session_factory, run_id)}
    duplicate = by_url["http://target.com/dup2.pdf"]
    assert duplicate.extraction_status is ExtractionStatus.skipped
    assert duplicate.skip_reason is SkipReason.duplicate_hash
    assert duplicate.file_hash_sha256 == by_url["http://target.com/dup1.pdf"].file_hash_sha256


async def test_too_large_empty_and_unsupported_are_skipped(
    session_factory, fake_public_dns, install_transport
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/big.pdf":
            # Declared over the limit: the HEAD probe alone triggers too_large.
            headers = {"content-type": "application/pdf", "content-length": str(60 * 1024 * 1024)}
            return (
                httpx.Response(200, headers=headers)
                if request.method == "HEAD"
                else (httpx.Response(200, headers=headers, content=b"x" * 10))
            )
        if path == "/empty.pdf":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"")
        if path == "/fake.pdf":
            body = b"<html><body>not a pdf</body></html>"
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf", "content-length": str(len(body))},
                content=b"" if request.method == "HEAD" else body,
            )
        return httpx.Response(404)

    install_transport(handler)
    run_id = await _make_run(
        session_factory,
        [
            "http://target.com/big.pdf",
            "http://target.com/empty.pdf",
            "http://target.com/fake.pdf",
        ],
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_skipped == 3
    by_url = {a.source_url: a for a in await _assets(session_factory, run_id)}
    assert by_url["http://target.com/big.pdf"].skip_reason is SkipReason.too_large
    assert by_url["http://target.com/empty.pdf"].skip_reason is SkipReason.empty_body
    fake = by_url["http://target.com/fake.pdf"]
    assert fake.skip_reason is SkipReason.unsupported_type
    # Magic bytes decided: the HTML body was never parsed as a PDF.
    async with session_factory() as session:
        assert await RawMetadataRepository(session).list_by_asset(fake.id) == []


async def test_max_assets_per_run_caps_downloads(
    session_factory, fake_public_dns, install_transport
) -> None:
    html = b"".join(f'<a href="/doc{i}.pdf">d</a>'.encode() for i in range(4))
    routes: RouteMap = {"/": (200, "text/html", html)}
    for i in range(4):
        # Distinct bytes per document: identical content would dedup by hash.
        routes[f"/doc{i}.pdf"] = (200, "application/pdf", make_pdf_bytes(title=f"Doc {i}"))
    install_transport(_routes(routes))
    run_id = await _make_run(session_factory, ["target.com"])
    summary = await IngestionPipeline(session_factory, _settings(max_assets_per_run=2)).execute(
        run_id
    )

    # The HTML page consumes one slot; one of the four PDFs is downloaded.
    assert summary.assets_ok == 2
    assert len(await _assets(session_factory, run_id)) == 2
    kinds = {asset.source_url for asset in await _assets(session_factory, run_id)}
    assert "https://target.com/" in kinds


async def test_redirect_out_of_scope_asset_is_skipped(
    session_factory, fake_public_dns, install_transport
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "evil.com":
            raise AssertionError("the off-scope host was requested")
        return httpx.Response(302, headers={"location": "http://evil.com/loot.pdf"})

    install_transport(handler)
    run_id = await _make_run(session_factory, ["http://target.com/redir.pdf"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_skipped == 1
    asset = (await _assets(session_factory, run_id))[0]
    assert asset.extraction_status is ExtractionStatus.skipped
    assert asset.skip_reason is SkipReason.out_of_scope


async def test_redirect_loop_asset_fails_but_run_completes(
    session_factory, fake_public_dns, install_transport
) -> None:
    """Regression: an in-scope redirect loop raises MetaTracerError base in the
    gateway; it must land as one failed asset, not abort the run."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/loop.pdf":
            return httpx.Response(302, headers={"location": "/loop.pdf"})
        return _routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)})(request)

    install_transport(handler)
    run_id = await _make_run(
        session_factory, ["http://target.com/loop.pdf", "http://target.com/doc.pdf"]
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert (summary.assets_ok, summary.assets_failed) == (1, 1)
    by_url = {a.source_url: a for a in await _assets(session_factory, run_id)}
    looped = by_url["http://target.com/loop.pdf"]
    assert looped.extraction_status is ExtractionStatus.failed
    assert "redirect limit" in (looped.error_message or "")
    assert by_url["http://target.com/doc.pdf"].extraction_status is ExtractionStatus.ok


async def test_unconfirmed_scope_aborts_before_any_http(
    session_factory, fake_public_dns, install_transport
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    install_transport(handler)
    run_id = await _make_run(session_factory, ["http://target.com/doc.pdf"], confirmed=False)
    with pytest.raises(ScopeNotConfirmedError):
        await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert await _assets(session_factory, run_id) == []


async def test_temp_files_are_deleted_and_bytes_never_persisted(
    session_factory, fake_public_dns, install_transport
) -> None:
    temp_dir = Path(tempfile.gettempdir())
    before = set(temp_dir.glob("metatracer-*"))
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    run_id = await _make_run(session_factory, ["http://target.com/doc.pdf"])
    await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert set(temp_dir.glob("metatracer-*")) == before  # no temp file left behind
    async with session_factory() as session:
        items = await RawMetadataRepository(session).list_by_run(run_id)
    # Only structured metadata text is stored — never file bytes.
    assert items
    assert all("%PDF" not in item.value for item in items)
    assert all(isinstance(item.value, str) for item in items)


# ---------------------------------------------------------------------------
# Fase 2: the crawl budget stops the crawl and records why.
#
# These are the tests that turn "nothing else was found" into a falsifiable
# claim: a run that hits a limit must say so, and must not download past it.
# ---------------------------------------------------------------------------


async def _run_with_budget(
    factory, targets: list[str], budget: dict[str, object]
) -> str:
    """Create a run whose persisted snapshot carries the given budget."""
    async with factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps(targets),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=True,
                ingestion_stats=json.dumps({"budget": budget, "limits_hit": []}),
            )
        )
        return run.id


async def _stats(factory, run_id: str) -> dict:
    async with factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None and run.ingestion_stats
    return json.loads(run.ingestion_stats)


async def test_asset_budget_stops_the_crawl_and_records_the_limit(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _routes(
            {
                "/page": (200, "text/html", b'<a href="/a.pdf">a</a><a href="/b.pdf">b</a>'),
                "/a.pdf": (200, "application/pdf", PDF_BYTES),
                "/b.pdf": (200, "application/pdf", PDF_BYTES),
            }
        )(request)

    install_transport(handler)
    # One page plus at most one document: the page itself consumes a slot.
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/page"],
        {"depth": 1, "max_pages": 1, "max_assets": 2, "max_total_bytes": 10_000_000},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "max_assets" in summary.limits_hit
    assert "/b.pdf" not in requested  # the limit stopped the request, not just the counter
    stats = await _stats(session_factory, run_id)
    assert "max_assets" in stats["limits_hit"]
    # The page itself consumes one slot, so exactly one document was queued and
    # the second link was dropped — and recorded as dropped.
    assert stats["assets_queued"] == 1
    assert stats["limits_hit"] == ["max_assets"]


async def test_page_budget_caps_pages(
    session_factory, fake_public_dns, install_transport
) -> None:
    installed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        installed.append(request.url.path)
        return _routes(
            {
                "/one": (200, "text/html", b"<p>one</p>"),
                "/two": (200, "text/html", b"<p>two</p>"),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/one", "http://target.com/two"],
        {"depth": 1, "max_pages": 1, "max_assets": 10, "max_total_bytes": 10_000_000},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.pages_crawled == 1
    assert "max_pages" in summary.limits_hit
    assert "/two" not in installed


async def test_byte_budget_is_recorded_with_the_real_transfer(
    session_factory, fake_public_dns, install_transport
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    # A budget smaller than the document: the transfer is charged and recorded.
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/doc.pdf"],
        {"depth": 1, "max_pages": 1, "max_assets": 10, "max_total_bytes": 10},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "max_total_bytes" in summary.limits_hit
    stats = await _stats(session_factory, run_id)
    assert stats["bytes_downloaded"] >= len(PDF_BYTES)


async def test_time_budget_stops_before_the_next_request(
    session_factory, fake_public_dns, install_transport, monkeypatch
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _routes({"/a.pdf": (200, "application/pdf", PDF_BYTES)})(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/a.pdf"],
        {"depth": 1, "max_pages": 1, "max_assets": 10, "max_total_bytes": 10_000_000},
    )
    # Simulate a run that already spent its wall-clock budget: patch the tracker
    # constructor so it starts far in the past. Freezing time.monotonic would
    # also freeze the elapsed calculation and prove nothing.
    real_tracker = BudgetTracker

    def aged_tracker(*args: object, **kwargs: object) -> BudgetTracker:
        kwargs.pop("started_at", None)
        return real_tracker(*args, started_at=time.monotonic() - 10_000, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("metatracer.extractors.ingest.BudgetTracker", aged_tracker)
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "max_seconds" in summary.limits_hit
    assert requested == []  # nothing was downloaded


async def test_a_run_without_a_snapshot_keeps_the_historical_defaults(
    session_factory, fake_public_dns, install_transport
) -> None:
    # Backwards compatibility: a run created before Fase 2 has no snapshot, so
    # the budget comes from Settings and the run behaves exactly as before.
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    run_id = await _make_run(session_factory, ["http://target.com/doc.pdf"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 1
    assert summary.limits_hit == ()
    stats = await _stats(session_factory, run_id)
    assert stats["budget"]["max_assets"] == 50  # Settings default
    assert stats["limits_hit"] == []


async def test_depth_one_does_not_follow_html_and_records_the_stop(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        body = b'<a href="/more.html">next</a><a href="/doc.pdf">d</a>'
        return _routes(
            {
                "/": (200, "text/html", body),
                "/more.html": (200, "text/html", b"<p>should not be fetched</p>"),
                "/doc.pdf": (200, "application/pdf", PDF_BYTES),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/"],
        {"depth": 1, "max_pages": 5, "max_assets": 10, "max_total_bytes": 10_000_000},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "/more.html" not in requested
    assert "/doc.pdf" in requested
    assert summary.pages_crawled == 1
    assert "max_depth" in summary.limits_hit


async def test_depth_two_follows_one_html_hop_and_stops(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        pages = {
            "/": b'<a href="/more.html">next</a><a href="/doc.pdf">d</a>',
            "/more.html": b'<a href="/deeper.html">further</a><a href="/nested.pdf">n</a>',
            "/deeper.html": b"<p>too deep</p>",
        }
        if request.url.path in pages:
            return _routes({request.url.path: (200, "text/html", pages[request.url.path])})(request)
        if request.url.path in ("/doc.pdf", "/nested.pdf"):
            return _routes({request.url.path: (200, "application/pdf", PDF_BYTES)})(request)
        return httpx.Response(404)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/"],
        {"depth": 2, "max_pages": 5, "max_assets": 10, "max_total_bytes": 10_000_000},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "/more.html" in requested
    assert "/nested.pdf" in requested
    assert "/deeper.html" not in requested
    assert summary.pages_crawled == 2
    assert "max_depth" in summary.limits_hit
    assets = await _assets(session_factory, run_id)
    urls = {asset.source_url for asset in assets}
    assert "http://target.com/nested.pdf" in urls
    assert "http://target.com/deeper.html" not in urls


async def test_page_cap_wins_over_remaining_depth(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        body = b'<a href="/more.html">next</a>'
        return _routes(
            {
                "/": (200, "text/html", body),
                "/more.html": (200, "text/html", b"<p>no</p>"),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/"],
        {"depth": 3, "max_pages": 1, "max_assets": 10, "max_total_bytes": 10_000_000},
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.pages_crawled == 1
    assert "/more.html" not in requested
    assert "max_pages" in summary.limits_hit


async def test_extensionless_url_is_probed_before_download(
    session_factory, fake_public_dns, install_transport
) -> None:
    """A ``/download?id=`` PDF is fetched; an extensionless HTML link is not."""
    downloaded: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/page":
            body = (
                b'<a href="/download?id=7">doc</a>'
                b'<a href="/section">nav</a>'
                b'<img srcset="/small.jpg 1x, /large.jpg 2x">'
            )
            return _routes({"/page": (200, "text/html", body)})(request)
        if path == "/download":
            if request.method == "GET":
                downloaded.append(path)
            return _routes({"/download": (200, "application/pdf", PDF_BYTES)})(request)
        if path == "/section":
            if request.method == "GET":
                downloaded.append(path)
            return httpx.Response(
                200, headers={"content-type": "text/html", "content-length": "12"}
            )
        if path == "/large.jpg":
            if request.method == "GET":
                downloaded.append(path)
            return _routes({"/large.jpg": (200, "image/jpeg", JPEG_BYTES)})(request)
        if path == "/small.jpg":
            downloaded.append(path)
            return httpx.Response(500)
        return httpx.Response(404)

    install_transport(handler)
    run_id = await _make_run(session_factory, ["http://target.com/page"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assets = await _assets(session_factory, run_id)
    by_url = {asset.source_url: asset for asset in assets}
    assert by_url["http://target.com/download?id=7"].extraction_status is ExtractionStatus.ok
    assert by_url["http://target.com/large.jpg"].extraction_status is ExtractionStatus.ok
    section = by_url["http://target.com/section"]
    assert section.extraction_status is ExtractionStatus.skipped
    assert section.skip_reason is SkipReason.unsupported_type
    assert "/section" not in downloaded  # HEAD rejected it; the body was not read
    assert "/small.jpg" not in downloaded  # the 1x candidate was never the one kept
    assert "/download" in downloaded and "/large.jpg" in downloaded
    assert summary.assets_ok >= 2


async def test_corrupt_snapshot_falls_back_instead_of_failing_the_run(
    session_factory, fake_public_dns, install_transport
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input=json.dumps(["http://target.com/doc.pdf"]),
                allowed_scope=json.dumps(["target.com"]),
                scope_confirmed=True,
                # A budget that cannot be constructed (depth 0 fails validation).
                ingestion_stats=json.dumps({"budget": {"depth": 0}, "limits_hit": []}),
            )
        )
        run_id = run.id
    # A corrupt snapshot must never abort the run: the assets get ingested.
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)
    assert summary.assets_ok == 1


# ---------------------------------------------------------------------------
# robots.txt is courtesy. It never widens scope, and a missing file does not
# stop the run.
# ---------------------------------------------------------------------------

_ROBOTS = (
    b"User-agent: *\n"
    b"Disallow: /private/\n"
    b"Sitemap: https://evil.com/sitemap.xml\n"
    b"Sitemap: http://target.com/sitemap.xml\n"
)
_SITEMAP = (
    b'<?xml version="1.0"?>'
    b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<url><loc>http://target.com/from-map.pdf</loc></url>"
    b"<url><loc>https://evil.com/loot.pdf</loc></url>"
    b"</urlset>"
)
_PAGE = b'<a href="/private/secret.pdf">s</a><a href="/public.pdf">p</a>'


def _robots_budget(**extra: object) -> dict[str, object]:
    budget: dict[str, object] = {
        "depth": 1,
        "max_pages": 1,
        "max_assets": 10,
        "max_total_bytes": 10_000_000,
        "honor_robots": True,
    }
    budget.update(extra)
    return budget


async def test_robots_disallow_is_courtesy_and_sitemaps_cannot_widen_scope(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.url.host, request.url.path))
        if request.url.host != "target.com":
            raise AssertionError("an off-scope host was requested")
        return _routes(
            {
                "/robots.txt": (200, "text/plain", _ROBOTS),
                "/sitemap.xml": (200, "application/xml", _SITEMAP),
                "/page": (200, "text/html", _PAGE),
                "/public.pdf": (200, "application/pdf", PDF_BYTES),
                "/from-map.pdf": (
                    200,
                    "application/pdf",
                    make_pdf_bytes(title="From the sitemap"),
                ),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory, ["http://target.com/page"], _robots_budget()
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    paths = {path for _host, path in requested}
    assert "/private/secret.pdf" not in paths
    assert "/public.pdf" in paths
    assert "/from-map.pdf" in paths
    assert "/robots.txt" in paths
    assert "/sitemap.xml" in paths
    by_url = {asset.source_url: asset for asset in await _assets(session_factory, run_id)}
    omitted = by_url["http://target.com/private/secret.pdf"]
    assert omitted.extraction_status is ExtractionStatus.skipped
    assert omitted.skip_reason is SkipReason.robots_disallow
    assert "courtesy" in (omitted.error_message or "")
    stats = await _stats(session_factory, run_id)
    assert stats["robots_checked"] is True
    assert stats["robots_omitted"] >= 1
    assert stats["sitemaps_ignored"] >= 1
    assert summary.assets_skipped >= 1
    assert summary.assets_ok >= 2


async def test_honor_robots_false_still_fetches_a_disallowed_path(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _routes(
            {
                "/robots.txt": (200, "text/plain", _ROBOTS),
                "/page": (200, "text/html", _PAGE),
                "/private/secret.pdf": (200, "application/pdf", PDF_BYTES),
                "/public.pdf": (200, "application/pdf", make_pdf_bytes(title="Public")),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory,
        ["http://target.com/page"],
        _robots_budget(honor_robots=False),
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "/robots.txt" not in requested
    assert "/private/secret.pdf" in requested
    assert summary.assets_ok >= 2
    stats = await _stats(session_factory, run_id)
    assert stats["robots_checked"] is False


async def test_unreadable_robots_does_not_fail_the_run(
    session_factory, fake_public_dns, install_transport
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(500)
        return _routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)})(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory, ["http://target.com/doc.pdf"], _robots_budget()
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 1
    assert summary.assets_failed == 0
    stats = await _stats(session_factory, run_id)
    assert stats["robots_checked"] is True
    assert stats["robots_omitted"] == 0


async def test_disallowed_page_is_not_fetched(
    session_factory, fake_public_dns, install_transport
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _routes(
            {
                "/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /hidden.html\n"),
                "/hidden.html": (200, "text/html", b"<a href='/doc.pdf'>d</a>"),
                "/doc.pdf": (200, "application/pdf", PDF_BYTES),
            }
        )(request)

    install_transport(handler)
    run_id = await _run_with_budget(
        session_factory, ["http://target.com/hidden.html"], _robots_budget()
    )
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert "/hidden.html" not in requested
    assert "/doc.pdf" not in requested
    assert summary.pages_crawled == 0
    assets = await _assets(session_factory, run_id)
    assert len(assets) == 1
    assert assets[0].skip_reason is SkipReason.robots_disallow


async def test_docx_properties_are_stored_and_the_body_is_not(
    session_factory, fake_public_dns, install_transport
) -> None:
    from tests.unit.test_office import _docx

    install_transport(
        _routes({"/report.docx": (200, "application/octet-stream", _docx())})
    )
    run_id = await _make_run(session_factory, ["http://target.com/report.docx"])
    summary = await IngestionPipeline(session_factory, _settings()).execute(run_id)

    assert summary.assets_ok == 1
    assets = await _assets(session_factory, run_id)
    assert assets[0].extraction_status is ExtractionStatus.ok
    async with session_factory() as session:
        items = await RawMetadataRepository(session).list_by_asset(assets[0].id)
    found = {(item.namespace, item.key): item.value for item in items}
    assert found[("ooxml", "dc:creator")] == "jane@acme.test"
    assert found[("ooxml", "app:Company")] == "Acme"
    assert all("SECRET-BODY-TOKEN" not in item.value for item in items)
