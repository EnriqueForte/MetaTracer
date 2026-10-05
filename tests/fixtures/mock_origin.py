"""Real loopback HTTP origin for the TASK-07 e2e tests (subtask 7.1).

A uvicorn server bound to ``127.0.0.1`` on an ephemeral port, serving the
synthetic fixtures of :mod:`tests.fixtures.generate_test_fixtures` plus HTML
index pages that link them — a stand-in for a real target's public site.

Loopback safety contract (inviolable rule 7): the NetworkSafetyGuard blocks
loopback addresses by default, so scans against this server only work with
``Settings(allow_loopback=True)`` — the in-process equivalent of
``METATRACER_ALLOW_LOOPBACK=true``. That flag exists ONLY for the test suite;
it is never enabled by the product, the Docker image or the Compose file.
One e2e test proves the default still rejects this very server.

The server counts requests per path, so tests can prove a negative: the
off-scope redirect target must show ZERO hits (the gateway validates the hop
before opening a socket and never reads a redirect body).
"""

import threading
import time
from collections import Counter
from collections.abc import Callable

import uvicorn

from tests.fixtures.generate_test_fixtures import build_fixture_files, spec_for

_STARTUP_TIMEOUT_S = 10.0
_SHUTDOWN_TIMEOUT_S = 5.0
_HTML = "text/html; charset=utf-8"
_JS = "application/javascript; charset=utf-8"

#: Redirect route linked from the index page; its Location leaves the scope.
REDIRECT_PATH = "/redirect/offscope.pdf"
#: Off-scope target of the redirect; reachable only if the gateway misbehaves.
SECRET_PATH = "/secret.pdf"
#: TASK-09 leaky HTML page (headers + meta + comments + script src).
LEAKY_PATH = "/leaky.html"
JS_PATH = "/static/app.js"

LEAKY_HTML = (
    b"<!doctype html>\n<html><head><title>Leaky page</title>"
    b'<meta name="generator" content="WordPress 6.4.2">'
    b'<meta name="author" content="recon@acme-corp.internal">'
    b"</head><body>\n"
    b"  <!-- TODO: remove staging credentials before go-live -->\n"
    b'  <script src="/static/app.js"></script>\n'
    b"</body></html>\n"
)
LEAKY_JS = b"/* FIXME: leftover debug path C:\\Users\\web_admin\\app.js */\nfunction boot(){}\n"


def _index_page(filenames: list[str], *, include_redirect: bool) -> bytes:
    """HTML page linking the given fixture files (and optionally the redirect)."""
    links = [f'    <li><a href="/files/{name}">{name}</a></li>' for name in filenames]
    if include_redirect:
        links.append(f'    <li><a href="{REDIRECT_PATH}">offscope.pdf (redirect)</a></li>')
    body = "\n".join(links)
    return (
        "<!doctype html>\n<html><head><title>Mock origin</title></head>"
        f"<body>\n  <h1>Fixture documents</h1>\n  <ul>\n{body}\n  </ul>\n</body></html>\n"
    ).encode()


class MockOrigin:
    """Lifecycle + request accounting for the loopback fixture server."""

    def __init__(self) -> None:
        self._files = build_fixture_files()
        self._hits: Counter[str] = Counter()
        self.port: int = 0
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """Root URL of the origin (only valid after :meth:`start`)."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def index_url(self) -> str:
        """Page linking every fixture plus the off-scope redirect."""
        return f"{self.base_url}/index.html"

    @property
    def clean_url(self) -> str:
        """Page linking only the two sanitized fixtures."""
        return f"{self.base_url}/clean.html"

    @property
    def leaky_url(self) -> str:
        """HTML page that leaks headers, generator, comments and a JS file."""
        return f"{self.base_url}{LEAKY_PATH}"

    def file_url(self, filename: str) -> str:
        return f"{self.base_url}/files/{filename}"

    def hits(self, path: str) -> int:
        """How many requests (any method) reached ``path``."""
        return self._hits.get(path, 0)

    @property
    def total_hits(self) -> int:
        return sum(self._hits.values())

    def start(self) -> None:
        """Start uvicorn in a daemon thread and wait until it accepts requests."""
        config = uvicorn.Config(
            self._asgi,
            host="127.0.0.1",
            port=0,
            log_level="error",
            access_log=False,
            interface="asgi3",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="metatracer-mock-origin", daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + _STARTUP_TIMEOUT_S
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("mock origin did not start in time")
            time.sleep(0.01)
        # Port 0 means the OS chose one; read it back from the listening socket.
        self.port = int(self._server.servers[0].sockets[0].getsockname()[1])

    def stop(self) -> None:
        """Ask uvicorn to exit and join its thread."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=_SHUTDOWN_TIMEOUT_S)

    async def _asgi(self, scope, receive, send) -> None:
        """Minimal ASGI app: lifespan handshake + the route table."""
        if scope["type"] == "lifespan":
            await _handle_lifespan(receive, send)
            return
        path = scope["path"]
        self._hits[path] += 1
        head_only = scope["method"] == "HEAD"
        handler = self._route(path)
        if handler is None:
            await self._respond(send, 404, "text/plain", b"not found", head_only)
            return
        await handler(send, head_only)

    def _route(self, path: str) -> Callable | None:
        if path in ("/", "/index.html"):
            page = _index_page(list(self._files), include_redirect=True)
            return lambda send, head: self._respond(send, 200, _HTML, page, head)
        if path == "/clean.html":
            clean = [name for name in self._files if not spec_for(name).expected_types]
            page = _index_page(clean, include_redirect=False)
            return lambda send, head: self._respond(send, 200, _HTML, page, head)
        if path == LEAKY_PATH:
            return lambda send, head: self._respond(
                send,
                200,
                _HTML,
                LEAKY_HTML,
                head,
                extra_headers={"x-powered-by": "PHP/8.2.0"},
            )
        if path == JS_PATH:
            return lambda send, head: self._respond(send, 200, _JS, LEAKY_JS, head)
        if path == REDIRECT_PATH:
            return lambda send, head: self._redirect(send)
        if path == SECRET_PATH:
            # Never legitimately reached: the redirect to here is off-scope, so
            # the gateway must reject the hop before opening the connection.
            return lambda send, head: self._respond(
                send, 200, "application/pdf", self._files["clean.pdf"], head
            )
        if path.startswith("/files/"):
            name = path.removeprefix("/files/")
            data = self._files.get(name)
            if data is None:
                return None
            content_type = spec_for(name).content_type
            return lambda send, head: self._respond(send, 200, content_type, data, head)
        return None

    async def _redirect(self, send) -> None:
        """302 to the same server under a DIFFERENT host name (out of scope).

        ``localhost`` resolves to this very machine, so a hit on SECRET_PATH is
        technically possible — which is exactly what makes its zero-hit count a
        meaningful proof that the gateway refused the hop before connecting.
        """
        await send(
            {
                "type": "http.response.start",
                "status": 302,
                "headers": [
                    (b"location", f"http://localhost:{self.port}{SECRET_PATH}".encode()),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _respond(
        send,
        status: int,
        content_type: str,
        body: bytes,
        head_only: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
        ]
        for name, value in (extra_headers or {}).items():
            headers.append((name.encode(), value.encode()))
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": b"" if head_only else body})


async def _handle_lifespan(receive, send) -> None:
    """Minimal lifespan handshake so uvicorn does not log it as unsupported."""
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return
