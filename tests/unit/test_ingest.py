"""IngestionPipeline end-to-end over a mocked transport (TASK-01 DoD).

Covers: pdfinfo/EXIF persistence linked to the asset, domain crawl with
rate-limited discovery, per-asset failure isolation, redirect-out-of-scope,
magic-byte allowlist, duplicate hashes, the global asset cap, temp-file
cleanup and the scope-confirmation gate. DNS and transport are faked;
ScopeValidator and NetworkSafetyGuard are the real ones.
"""

import json
import tempfile
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
