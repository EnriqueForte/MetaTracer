"""TASK-32: loopback kill-switch, SSRF ranges, IDN scopes, limiter, extractors."""

import asyncio
import os
import socket
import tempfile
import time
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from metatracer.core.config import Settings, enforce_loopback_test_only, get_settings
from metatracer.core.exceptions import LoopbackOutsideTestsError, SecurityViolationError
from metatracer.core.ratelimit import ApiRateLimiter
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.scope import ScopeValidator, assert_registrable_scope, normalize_host
from metatracer.extractors.crawler import _sniff_html
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.ingest import sweep_stale_tempfiles
from metatracer.extractors.javascript import extract_js_comments
from metatracer.services.orchestrator import ScanRequest
from tests.unit.test_ratelimit import _request


def test_allow_loopback_outside_pytest_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("METATRACER_ALLOW_LOOPBACK", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(LoopbackOutsideTestsError):
            get_settings()
        with pytest.raises(LoopbackOutsideTestsError):
            enforce_loopback_test_only(Settings(_env_file=None, allow_loopback=True))
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "address",
    [
        "0.1.2.3",
        "192.0.0.8",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "198.18.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "2001:db8::1",
        "100::1",
    ],
)
async def test_guard_blocks_reserved_ranges(
    address: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(host, port, family=0, socktype=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check("reserved.example")


@pytest.mark.parametrize(
    "host",
    ["2130706433", "0177.0.0.1", "0x7f.0.0.1", "0x7f000001", "127.1", "10.1"],
)
async def test_noncanonical_ipv4_is_refused_before_dns(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("DNS must not run for a non-canonical IPv4 host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard().check(host)


async def test_allow_loopback_still_blocks_reserved_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(host, port, family=0, socktype=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    with pytest.raises(SecurityViolationError):
        await NetworkSafetyGuard(allow_loopback=True).check("docs.example")


def test_idn_scope_matches_punycode_and_the_reverse() -> None:
    assert normalize_host("https://münchen.de/a") == "xn--mnchen-3ya.de"
    assert normalize_host("xn--mnchen-3ya.de") == "xn--mnchen-3ya.de"
    assert ScopeValidator(["münchen.de"]).is_in_scope("https://xn--mnchen-3ya.de/x")
    assert ScopeValidator(["xn--mnchen-3ya.de"]).is_in_scope("https://münchen.de/x")


def test_single_label_scope_is_rejected() -> None:
    with pytest.raises(ValueError):
        assert_registrable_scope("com")
    with pytest.raises(ValueError):
        assert_registrable_scope("*.com")
    with pytest.raises(ValidationError):
        ScanRequest(
            targets=["https://target.com/a.pdf"],
            scope_domains=["*.com"],
            scope_confirmed=True,
        )


def test_public_suffix_is_warned(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert_registrable_scope("co.uk")
    assert any("public suffix" in message for message in caplog.messages)


async def test_concurrent_checks_are_not_serialized_by_an_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[bool] = []
    original = asyncio.sleep

    async def spy(delay, *args, **kwargs):
        limiter_locked = limiter._lock.locked()
        sleeps.append(limiter_locked)
        await original(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", spy)
    limiter = ApiRateLimiter(8)
    started = time.perf_counter()
    await asyncio.gather(*(limiter.check(_request()) for _ in range(8)))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.3
    assert sleeps == [] or not any(sleeps)


def test_deeply_nested_template_does_not_recurse() -> None:
    source = "// TODO: kept\n`" + ("${" * 10_000) + "1" + ("}" * 10_000) + "`"
    comments = extract_js_comments(source)
    assert any("TODO: kept" in item for item in comments)


def test_image_over_pixel_ceiling_raises(tmp_path: Path) -> None:
    path = tmp_path / "wide.png"
    Image.new("RGB", (8, 8), "white").save(path)
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 1
    try:
        from metatracer.core.exceptions import ExtractionError

        with pytest.raises(ExtractionError, match="image"):
            ImageMetadataExtractor().extract(path)
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def test_empty_content_type_sniffs_html() -> None:
    assert _sniff_html(b"  <!DOCTYPE html><html></html>")
    assert _sniff_html(b"<HTML><body>")
    assert not _sniff_html(b"%PDF-1.7")


def test_sweep_deletes_only_stale_metatracer_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / "metatracer-old"
    fresh = tmp_path / "metatracer-new"
    other = tmp_path / "notes.txt"
    folder = tmp_path / "metatracer-dir"
    stale.write_text("x")
    fresh.write_text("y")
    other.write_text("z")
    folder.mkdir()
    old = time.time() - 7200
    os.utime(stale, (old, old))
    assert sweep_stale_tempfiles() == 1
    assert not stale.exists()
    assert fresh.exists() and other.exists() and folder.is_dir()
