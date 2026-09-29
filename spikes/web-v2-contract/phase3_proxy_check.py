"""Phase 3: cookie and SSE behavior through the Next /api rewrite."""

from __future__ import annotations

import json
import http.client

API = ("127.0.0.1", 8765)
WEB = ("127.0.0.1", 3456)


def raw(host: tuple[str, int], method: str, path: str, body: dict | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection(*host, timeout=20)
    payload = None if body is None else json.dumps(body)
    hdrs = {"content-type": "application/json"} if body is not None else {}
    hdrs.update(headers or {})
    conn.request(method, path, body=payload, headers=hdrs)
    response = conn.getresponse()
    chunks = []
    # Read a little, then more if the stream stays open briefly.
    chunks.append(response.read(800))
    print(f"\n{host[1]} {method} {path} -> {response.status}")
    for key, value in response.getheaders():
        if key.lower() in {"set-cookie", "content-security-policy", "x-accel-buffering", "content-type"}:
            print(f"  {key}: {value[:180]}")
    text = b"".join(chunks)
    print("  body:", text[:300])
    conn.close()
    return response.status, response.getheaders(), text


def cookie_from(headers, name: str) -> str:
    for key, value in headers:
        if key.lower() == "set-cookie" and value.startswith(name + "="):
            return value.split(";", 1)[0].split("=", 1)[1]
    return ""


status, headers, _ = raw(API, "GET", "/login")
csrf = cookie_from(headers, "csrf_token")
print("csrf from /login", bool(csrf))

status, headers, body = raw(
    WEB,
    "POST",
    "/api/auth/login",
    {"username": "operator", "password": "phase3-test-pass"},
    {"x-csrf-token": csrf, "cookie": f"csrf_token={csrf}"},
)
print("session cookie via rewrite", cookie_from(headers, "metatracer_session") != "")
print("csrf rotated via rewrite", cookie_from(headers, "csrf_token") != "")

session = cookie_from(headers, "metatracer_session")
csrf2 = cookie_from(headers, "csrf_token") or csrf
if session:
    status, headers, body = raw(
        WEB,
        "POST",
        "/api/runs",
        {
            "targets": ["http://127.0.0.1:9/"],
            "scope_domains": ["127.0.0.1"],
            "scope_confirmed": True,
            "reasoning_depth": "brief",
        },
        {
            "x-csrf-token": csrf2,
            "cookie": f"metatracer_session={session}; csrf_token={csrf2}",
        },
    )
    if status == 202:
        run_id = json.loads(body)["run_id"]
        raw(WEB, "GET", f"/api/runs/{run_id}/stream", headers={
            "cookie": f"metatracer_session={session}; csrf_token={csrf2}",
            "accept": "text/event-stream",
        })
