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
    """The orchestrator is already at its concurrency limit.

    Default limit is 1 (the historical single-scan lock: SQLite has a single
    writer, tasks README known trap 6). Since TASK-23 (Eje B) the limit is
    ``METATRACER_MAX_CONCURRENT_RUNS`` and this error fires when every slot
    is busy. The API maps it to HTTP 409 either way.
    """

    def __init__(self, active_run_ids: list[str] | None) -> None:
        self.active_run_ids: list[str] = list(active_run_ids or [])
        # Backward-compatible single-id view (first active run, if any).
        self.active_run_id: str | None = self.active_run_ids[0] if self.active_run_ids else None
        if self.active_run_ids:
            detail = ", ".join(self.active_run_ids)
            super().__init__(
                f"maximum concurrent scans reached (active run_id(s): {detail}); "
                "wait for one to finish or raise METATRACER_MAX_CONCURRENT_RUNS"
            )
        else:
            super().__init__(
                "maximum concurrent scans reached; wait for one to finish "
                "or raise METATRACER_MAX_CONCURRENT_RUNS"
            )
