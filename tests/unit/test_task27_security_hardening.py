"""TASK-27 P0 hardening: proxy bypass, public bind, HMAC, CSV formulas, XMP cap."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import socket
import zlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, EncodedStreamObject, NameObject
from typer.testing import CliRunner

from metatracer.api.webhooks import WebhookDispatcher, _public
from metatracer.cli.main import app as cli_app
from metatracer.core.bind_auth import (
    enforce_public_bind_auth,
    enforce_public_bind_from_env,
    is_loopback_bind,
)
from metatracer.core.config import Settings
from metatracer.core.exceptions import UnauthenticatedPublicBindError
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import DomainRateLimiter, safe_httpx_request
from metatracer.core.safety.scope import ScopeValidator
from metatracer.db.models import (
    Confidence,
    FindingType,
    ReasoningDepth,
    RunStatus,
    Severity,
    WebhookConfig,
)
from metatracer.extractors.pdf import PdfMetadataExtractor
from metatracer.extractors.xmp import MAX_XMP_PACKET_BYTES
from metatracer.reports.builder import ReportData, ReportFindingData, SeverityCounts
from metatracer.reports.csv_exporter import CsvReportExporter
from tests.fixtures.builders import XMP_PACKET

_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


# --- 27.1 environment proxies -------------------------------------------------


async def test_safe_http_ignores_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTPS_PROXY must not receive the socket; the client sets trust_env=False."""
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _PUBLIC_ADDRINFO)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "127.0.0.1":
            raise AssertionError("request was sent to the proxy")
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"ok")

    real_client = httpx.AsyncClient

    def factory(**kwargs):
        seen["trust_env"] = kwargs.get("trust_env")
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    response = await safe_httpx_request(
        "http://target.com/a.pdf",
        scope=ScopeValidator(["target.com"]),
        guard=NetworkSafetyGuard(allow_loopback=False),
        rate_limiter=DomainRateLimiter(1000.0),
        scope_confirmed=True,
    )
    assert seen["trust_env"] is False
    assert seen["url"] == "http://target.com/a.pdf"
    assert response.status_code == 200


# --- 27.2 public bind ---------------------------------------------------------


def test_loopback_names_and_unspecified_addresses() -> None:
    assert is_loopback_bind("127.0.0.1")
    assert is_loopback_bind("127.0.0.2")
    assert is_loopback_bind("localhost")
    assert is_loopback_bind("::1")
    assert is_loopback_bind("[::1]")
    assert is_loopback_bind("0.0.0.0") is False
    assert is_loopback_bind("::") is False


def test_public_bind_without_auth_is_refused() -> None:
    settings = _settings(auth_enabled=False, allow_unauthenticated_bind=False)
    with pytest.raises(UnauthenticatedPublicBindError, match="refusing to bind"):
        enforce_public_bind_auth(settings, "0.0.0.0")


def test_public_bind_with_auth_starts() -> None:
    settings = _settings(auth_enabled=True, allow_unauthenticated_bind=False)
    enforce_public_bind_auth(settings, "0.0.0.0")


def test_loopback_bind_allows_auth_off() -> None:
    settings = _settings(auth_enabled=False, allow_unauthenticated_bind=False)
    enforce_public_bind_auth(settings, "127.0.0.1")
    enforce_public_bind_auth(settings, "localhost")


def test_unauthenticated_bind_escape_logs_warning() -> None:
    settings = _settings(auth_enabled=False, allow_unauthenticated_bind=True)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)  # type: ignore[method-assign]
    logger = logging.getLogger("metatracer.core.bind_auth")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        enforce_public_bind_auth(settings, "0.0.0.0")
    finally:
        logger.removeHandler(handler)
    assert any("METATRACER_ALLOW_UNAUTHENTICATED_BIND" in record.getMessage() for record in records)


def test_serve_refuses_public_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "metatracer.cli.main.Settings",
        lambda: _settings(auth_enabled=False, allow_unauthenticated_bind=False),
    )
    started = {"ran": False}

    def _run(*args, **kwargs):
        started["ran"] = True

    monkeypatch.setattr(uvicorn, "run", _run)
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0", "--port", "9"])
    text = (result.output or "") + (result.stderr or "")
    assert result.exit_code == 1
    assert started["ran"] is False
    assert "refusing to bind" in text


def test_serve_escape_names_the_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "metatracer.cli.main.Settings",
        lambda: _settings(
            auth_enabled=False,
            allow_unauthenticated_bind=True,
            bind_host="127.0.0.1",
        ),
    )
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    result = CliRunner().invoke(cli_app, ["serve", "--host", "0.0.0.0", "--port", "9"])
    text = (result.output or "") + (result.stderr or "")
    assert result.exit_code == 0
    assert "ALLOW_UNAUTHENTICATED_BIND" in text


def test_serve_loopback_reaches_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "metatracer.cli.main.Settings",
        lambda: _settings(auth_enabled=False, bind_host="127.0.0.1"),
    )
    seen: dict[str, object] = {}

    def _run(*args, **kwargs):
        seen["host"] = kwargs.get("host")

    monkeypatch.setattr(uvicorn, "run", _run)
    result = CliRunner().invoke(cli_app, ["serve", "--port", "9"])
    assert result.exit_code == 0
    assert seen["host"] == "127.0.0.1"


def test_docker_entrypoint_refuses_public_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "metatracer.core.bind_auth.Settings",
        lambda: _settings(
            auth_enabled=False,
            bind_host="0.0.0.0",
            allow_unauthenticated_bind=False,
        ),
    )
    with pytest.raises(SystemExit) as exc:
        enforce_public_bind_from_env()
    assert exc.value.code == 1


# --- 27.3 webhook HMAC --------------------------------------------------------


class _AllowGuard:
    async def check(self, host: str, port: int) -> None:
        return None


def _capture_client(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "127.0.0.1":
            raise AssertionError("request was sent to the proxy")
        seen["body"] = request.content
        seen["timestamp"] = request.headers.get("x-metatracer-timestamp")
        seen["signature"] = request.headers.get("x-metatracer-signature")
        return httpx.Response(204)

    def factory(**kwargs):
        seen["trust_env"] = kwargs.get("trust_env")
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def test_webhook_signature_matches_raw_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _capture_client(monkeypatch, seen)
    dispatcher = WebhookDispatcher(None, guard=_AllowGuard())
    config = WebhookConfig(
        url="https://hooks.example.com/wh",
        event=RunStatus.completed,
        signature_secret="supersecret",
    )
    status_code, error = await dispatcher._send(config, {"b": 1, "a": "x"})
    assert error is None
    assert status_code == 204
    assert seen["trust_env"] is False
    body = seen["body"]
    assert isinstance(body, bytes)
    timestamp = seen["timestamp"]
    assert isinstance(timestamp, str) and timestamp.isdigit()
    expected_body = json.dumps(
        {"b": 1, "a": "x"}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    assert body == expected_body
    mac = hmac.new(
        b"supersecret", timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    assert seen["signature"] == f"sha256={mac}"


async def test_webhook_without_secret_has_no_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _capture_client(monkeypatch, seen)
    dispatcher = WebhookDispatcher(None, guard=_AllowGuard())
    config = WebhookConfig(url="https://hooks.example.com/wh", event=RunStatus.completed)
    status_code, error = await dispatcher._send(config, {"run_id": "r1"})
    assert error is None and status_code == 204
    assert seen["signature"] is None
    assert seen["timestamp"] is None


async def test_legacy_hash_only_webhook_is_unsigned(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _capture_client(monkeypatch, seen)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)  # type: ignore[method-assign]
    logger = logging.getLogger("metatracer.api.webhooks")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        dispatcher = WebhookDispatcher(None, guard=_AllowGuard())
        config = WebhookConfig(
            url="https://hooks.example.com/wh",
            event=RunStatus.completed,
            signature_secret_hash="abc",
        )
        status_code, error = await dispatcher._send(config, {"run_id": "r1"})
    finally:
        logger.removeHandler(handler)
    assert error is None and status_code == 204
    assert seen["signature"] is None
    assert any("legacy signature hash" in record.getMessage() for record in records)


def test_public_webhook_view_never_returns_the_secret() -> None:
    active = _public(
        WebhookConfig(
            url="https://hooks.example.com/wh",
            signature_secret="supersecret",
            signature_secret_hash="hash",
        )
    )
    legacy = _public(
        WebhookConfig(url="https://hooks.example.com/wh", signature_secret_hash="hash")
    )
    empty = _public(WebhookConfig(url="https://hooks.example.com/wh"))
    assert active["signature_status"] == "active"
    assert legacy["signature_status"] == "needs_secret"
    assert empty["signature_status"] == "none"
    dumped = json.dumps([active, legacy, empty])
    assert "supersecret" not in dumped
    assert "signature_secret" not in active


# --- 27.4 CSV formula neutralization ------------------------------------------


def _report(findings: tuple[ReportFindingData, ...]) -> ReportData:
    return ReportData(
        metatracer_version="0.6.0",
        run_id="run-1",
        target="target.example",
        scope=("target.example",),
        generated_at=datetime(2026, 10, 3, tzinfo=UTC),
        reasoning_depth=ReasoningDepth.standard,
        total_assets=1,
        severity_counts=SeverityCounts(),
        hygiene_note="note",
        compliance_notice="notice",
        findings=findings,
    )


def _card(**overrides) -> ReportFindingData:
    values = {
        "id": "f1",
        "title": "Title",
        "finding_type": FindingType.email,
        "type_label": "Email",
        "severity": Severity.low,
        "confidence": Confidence.high,
        "asset_source_url": "https://target.example/a.pdf",
        "asset_final_url": "https://target.example/a.pdf",
        "asset_content_type": "application/pdf",
        "field_source": "pdfinfo:Author",
        "evidence": "jane@target.example",
        "impact": "Plain impact",
        "explanation": "Plain explanation",
        "remediation": "Plain remediation",
        "reproduction_steps": (),
    }
    return ReportFindingData(**(values | overrides))


def test_csv_prefixes_formula_cells(tmp_path: Path) -> None:
    data = _report(
        (
            _card(id="eq", evidence="=1+1"),
            _card(id="at", evidence="@SUM(A1)"),
            _card(id="minus", evidence="-2+3"),
            _card(id="plus", evidence="+cmd"),
            _card(id="tab", evidence="\tcmd"),
            _card(id="cr", evidence="\rcmd"),
            _card(id="plain", evidence="jane@target.example"),
        )
    )
    path = CsvReportExporter(tmp_path).export(data)
    import csv

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row["evidence"]: row for row in rows}
    assert by_id["'=1+1"]["evidence"] == "'=1+1"
    assert "'@SUM(A1)" in {row["evidence"] for row in rows}
    assert "'-2+3" in {row["evidence"] for row in rows}
    assert "'+cmd" in {row["evidence"] for row in rows}
    assert "'\tcmd" in {row["evidence"] for row in rows}
    assert "'\rcmd" in {row["evidence"] for row in rows}
    assert "jane@target.example" in {row["evidence"] for row in rows}
    assert all(not row["impact"].startswith("'") for row in rows)


# --- 27.5 XMP inflate cap -----------------------------------------------------


def _pdf_with_metadata_stream(payload: bytes, filters: list[str]) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    writer.add_metadata({"/Author": "Jane Doe", "/Title": "Bounded XMP"})
    stream = EncodedStreamObject()
    stream[NameObject("/Type")] = NameObject("/Metadata")
    stream[NameObject("/Subtype")] = NameObject("/XML")
    if len(filters) == 1:
        stream[NameObject("/Filter")] = NameObject("/" + filters[0])
    else:
        stream[NameObject("/Filter")] = ArrayObject(
            [NameObject("/" + name) for name in filters]
        )
    stream._data = zlib.compress(payload) if filters == ["FlateDecode"] else b"not-flate"
    writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _extract(tmp_path: Path, content: bytes, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "doc.pdf"
    path.write_bytes(content)
    decoded = {"called": False}

    def _boom(*args, **kwargs):
        decoded["called"] = True
        raise RuntimeError("unbounded inflate")

    monkeypatch.setattr("pypdf.filters.decode_stream_data", _boom)
    limits: list[int] = []
    real = zlib.decompressobj

    class _Capped:
        def __init__(self, *args, **kwargs) -> None:
            self._inner = real(*args, **kwargs)

        def decompress(self, data: bytes, max_length: int = -1) -> bytes:
            limits.append(max_length)
            return self._inner.decompress(data, max_length)

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    monkeypatch.setattr(zlib, "decompressobj", lambda *args, **kwargs: _Capped(*args, **kwargs))
    fields = PdfMetadataExtractor().extract(path)
    return fields, decoded["called"], limits


def test_flate_xmp_bomb_keeps_pdfinfo_and_bounds_inflate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"A" * (MAX_XMP_PACKET_BYTES + 1024)
    content = _pdf_with_metadata_stream(payload, ["FlateDecode"])
    fields, decoded, limits = _extract(tmp_path, content, monkeypatch)
    by_ns = {field.namespace for field in fields}
    assert "pdfinfo" in by_ns
    assert "xmp" not in by_ns
    assert any(field.key == "Author" and field.value == "Jane Doe" for field in fields)
    assert decoded is False
    assert MAX_XMP_PACKET_BYTES + 1 in limits


def test_small_flate_xmp_is_still_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _pdf_with_metadata_stream(XMP_PACKET.encode("utf-8"), ["FlateDecode"])
    fields, decoded, _limits = _extract(tmp_path, content, monkeypatch)
    assert decoded is False
    assert any(
        field.namespace == "xmp" and field.key == "xmp:CreatorTool" for field in fields
    )


def test_non_flate_xmp_filter_is_discarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _pdf_with_metadata_stream(b"<x/>", ["LZWDecode"])
    fields, decoded, limits = _extract(tmp_path, content, monkeypatch)
    assert decoded is False
    assert MAX_XMP_PACKET_BYTES + 1 not in limits
    assert any(field.namespace == "pdfinfo" for field in fields)
    assert all(field.namespace != "xmp" for field in fields)


def test_filter_chain_xmp_is_discarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _pdf_with_metadata_stream(b"<x/>", ["FlateDecode", "ASCII85Decode"])
    fields, decoded, limits = _extract(tmp_path, content, monkeypatch)
    assert decoded is False
    assert MAX_XMP_PACKET_BYTES + 1 not in limits
    assert all(field.namespace != "xmp" for field in fields)
