"""HTTP header allowlist (TASK-09, subtask 9.2)."""

from metatracer.extractors.headers import extract_http_headers


def test_allowlisted_headers_persisted_lowercase() -> None:
    fields = extract_http_headers(
        {
            "Server": "nginx/1.18.0",
            "X-Powered-By": "PHP/8.2.0",
            "Content-Type": "text/html",
        }
    )
    by_key = {(field.namespace, field.key): field.value for field in fields}
    assert by_key == {
        ("http", "server"): "nginx/1.18.0",
        ("http", "x-powered-by"): "PHP/8.2.0",
    }


def test_auth_and_cookie_headers_are_dropped() -> None:
    fields = extract_http_headers(
        {
            "server": "nginx/1.18.0",
            "set-cookie": "session=secret",
            "authorization": "Bearer leaked",
            "cookie": "sid=1",
            "www-authenticate": "Basic realm=x",
        }
    )
    assert [(field.key, field.value) for field in fields] == [("server", "nginx/1.18.0")]
    joined = " ".join(field.value for field in fields)
    assert "secret" not in joined
    assert "Bearer" not in joined
