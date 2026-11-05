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


class LoopbackOutsideTestsError(MetaTracerError):
    """``METATRACER_ALLOW_LOOPBACK`` is set outside the test suite.

    TASK-32. The flag exists so pytest can reach a local mock server. A
    serve, scan or watch process refuses to start when it is set and
    ``PYTEST_CURRENT_TEST`` is absent.
    """


class UnauthenticatedPublicBindError(MetaTracerError):
    """Refusing to listen on a non-loopback address while authentication is off.

    TASK-27. The escape hatch is ``METATRACER_ALLOW_UNAUTHENTICATED_BIND``; it
    is logged and does not disable scope checks or the network safety guard.
    """


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


class RunNotAbortableError(MetaTracerError):
    """The run exists but is already in a terminal status (TASK-28)."""

    def __init__(self, run_id: str, status: str) -> None:
        self.run_id = run_id
        self.status = status
        super().__init__(f"run {run_id} is already {status}")


class RunNotResumableError(MetaTracerError):
    """Only an ``aborted`` run can be re-queued (TASK-41)."""

    def __init__(self, run_id: str, status: str) -> None:
        self.run_id = run_id
        self.status = status
        super().__init__(f"run {run_id} is {status}; only aborted runs can be resumed")


class RunActiveError(MetaTracerError):
    """A pending or running scan cannot be deleted (TASK-30)."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"run {run_id} is still active")


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


class InvestigationConflictError(MetaTracerError):
    """A run cannot be grouped, or an investigation name is already taken.

    The API maps this to HTTP 409. It is not an authorization decision:
    another investigation in the same install is visible, it just already
    owns the run or the name.
    """


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
