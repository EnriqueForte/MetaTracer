"""Browser security headers: policy shape and when HSTS is attached."""

from starlette.requests import Request

from metatracer.api.security_headers import CONTENT_SECURITY_POLICY, security_headers


def _request(
    scheme: str = "http",
    host: str = "testclient",
    forwarded_proto: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": (host, 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_baseline_policy_blocks_framing_and_foreign_scripts() -> None:
    headers = security_headers(_request())
    policy = headers["content-security-policy"]
    assert policy == CONTENT_SECURITY_POLICY
    assert "https://" not in policy
    assert "cdn.tailwindcss.com" not in policy
    assert "cdn.jsdelivr.net" not in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "upgrade-insecure-requests" not in policy
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in headers["permissions-policy"]
    assert "strict-transport-security" not in headers


def test_hsts_is_absent_on_plain_http_and_local_https() -> None:
    assert "strict-transport-security" not in security_headers(_request())
    assert "strict-transport-security" not in security_headers(
        _request(scheme="https", host="127.0.0.1")
    )


def test_hsts_is_sent_for_proxied_https() -> None:
    headers = security_headers(_request(forwarded_proto="https"))
    assert headers["strict-transport-security"].startswith("max-age=")
    assert "includeSubDomains" not in headers["strict-transport-security"]
    assert "preload" not in headers["strict-transport-security"]
