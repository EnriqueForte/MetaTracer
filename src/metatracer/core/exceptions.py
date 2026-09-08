"""Domain exception hierarchy. Every MetaTracer error derives from MetaTracerError."""


class MetaTracerError(Exception):
    """Base class for all MetaTracer errors."""


class OutOfScopeError(MetaTracerError):
    """A host or URL is not covered by the confirmed scope."""


class RedirectOutOfScopeError(OutOfScopeError):
    """A redirect hop points outside the confirmed scope.

    Subclasses OutOfScopeError so callers may catch either; raised before the
    body of the redirecting response is read.
    """


class SecurityViolationError(MetaTracerError):
    """The safety guard blocked an operation (SSRF, blocked IP range, bad scheme)."""


class ScopeNotConfirmedError(MetaTracerError):
    """A network operation was attempted with scope_confirmed=False."""


class ExtractionError(MetaTracerError):
    """Metadata extraction failed for an asset."""


class UnsupportedAssetError(MetaTracerError):
    """The asset type is not supported by any extractor."""


class AgentUnavailableError(MetaTracerError):
    """The LLM agent is not reachable or not configured."""


class RunNotFoundError(MetaTracerError):
    """No persisted run matches the given id or unique prefix."""

    def __init__(self, token: str) -> None:
        self.token = token
        super().__init__(f"run not found: {token}")


class ScopeNotFoundError(MetaTracerError):
    """No persisted scope matches the given id (TASK-10, v2.0)."""

    def __init__(self, token: str) -> None:
        self.token = token
        super().__init__(f"scope not found: {token}")


class AmbiguousRunError(MetaTracerError):
    """A short run-id prefix matches more than one persisted run."""

    def __init__(self, token: str, matches: list[str]) -> None:
        self.token = token
        self.matches = matches
        super().__init__(
            f"ambiguous run prefix {token!r}: matches {', '.join(matches)}; "
            "pass more characters or the full UUID"
        )


class ScanAlreadyRunningError(MetaTracerError):
    """A second scan was requested while another run holds the single-scan lock.

    SQLite has a single writer, so one process runs one scan at a time (tasks
    README, known trap 6); the API maps this error to HTTP 409.
    """

    def __init__(self, active_run_id: str | None) -> None:
        self.active_run_id = active_run_id
        super().__init__(
            f"a scan is already running (run_id={active_run_id or 'unknown'}); "
            "wait for it to finish before starting another"
        )
