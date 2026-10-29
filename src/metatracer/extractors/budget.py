"""Crawl budget: the explicit, auditable limits of one run (Fase 2).

Before this module the only caps were ``max_assets_per_run`` and
``max_file_bytes``; depth, pages, wall time, total bytes and download
concurrency were either hard-coded constants or absent. Because none of them
were recorded, a run could not say "I stopped because I hit a limit" — the UI
and the report could only show what had been processed, which reads as "that is
all there is". That is the honesty gap this module closes.

Two objects, deliberately separate:

- :class:`CrawlBudget` is **frozen**: the operator's configuration, validated
  once. It never changes during a run, so a log line can quote it verbatim.
- :class:`BudgetTracker` is **mutable** counters plus the list of limits that
  were actually reached. "Reached" is recorded, never inferred: the pipeline
  calls :meth:`BudgetTracker.charge_*` and reads :meth:`BudgetTracker.exhausted`
  before the next network request.

Nothing here performs I/O or imports a safety control: the tracker only decides
"may I do one more?", and the caller still goes through ``safe_httpx_request``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Hard ceilings for the *configuration* (not the run). They keep a typo like
# `max_assets=100000` from turning an audit into a scrape, and they are the
# bounds the API advertises.
MAX_DEPTH = 3
MAX_PAGES = 200
MAX_ASSETS_CEILING = 500
MAX_TOTAL_BYTES_CEILING = 2 * 1024 * 1024 * 1024  # 2 GiB
MAX_SECONDS_CEILING = 6 * 3600
MAX_CONCURRENCY_CEILING = 8

DEFAULT_DEPTH = 1
DEFAULT_PAGES = 1
DEFAULT_ASSETS = 50
DEFAULT_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MiB
DEFAULT_SECONDS = 900
DEFAULT_CONCURRENCY = 3

# Stable identifiers of the limits, as recorded in `limits_hit` and shown in the
# UI/report. Never invent a new spelling: the frontend and the report match on
# these strings.
LIMIT_DEPTH = "max_depth"
LIMIT_PAGES = "max_pages"
LIMIT_ASSETS = "max_assets"
LIMIT_BYTES = "max_total_bytes"
LIMIT_SECONDS = "max_seconds"


def _clamp(value: int, low: int, high: int, name: str) -> int:
    if value < low:
        raise ValueError(f"{name} must be >= {low}, got {value}")
    if value > high:
        raise ValueError(f"{name} must be <= {high}, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class CrawlBudget:
    """The operator's crawl limits for one run; validated on construction.

    Defaults reproduce the historical behaviour exactly for the caps that
    existed (one page, 50 assets) so an unconfigured run is not silently
    wider than before. The new limits default to values that a normal
    one-page audit never reaches.
    """

    depth: int = DEFAULT_DEPTH
    max_pages: int = DEFAULT_PAGES
    max_assets: int = DEFAULT_ASSETS
    max_total_bytes: int = DEFAULT_TOTAL_BYTES
    max_seconds: int = DEFAULT_SECONDS
    max_concurrency: int = DEFAULT_CONCURRENCY
    # Courtesy, on by default. A missing robots.txt changes nothing. Disallow
    # omits a URL; it never authorizes one. Set false to request an in-scope
    # path that robots would otherwise skip.
    honor_robots: bool = True

    def __post_init__(self) -> None:
        # Frozen dataclass: validation happens once, at construction, and the
        # object is then safe to share across the pipeline.
        _clamp(self.depth, 1, MAX_DEPTH, "depth")
        _clamp(self.max_pages, 1, MAX_PAGES, "max_pages")
        _clamp(self.max_assets, 1, MAX_ASSETS_CEILING, "max_assets")
        _clamp(self.max_total_bytes, 1, MAX_TOTAL_BYTES_CEILING, "max_total_bytes")
        _clamp(self.max_seconds, 1, MAX_SECONDS_CEILING, "max_seconds")
        _clamp(self.max_concurrency, 1, MAX_CONCURRENCY_CEILING, "max_concurrency")
        if not isinstance(self.honor_robots, bool):
            raise ValueError("honor_robots must be a bool")

    @classmethod
    def from_settings(cls, settings: object) -> CrawlBudget:
        """Build from ``Settings``, clamping rather than raising.

        A deployment that already sets ``METATRACER_MAX_ASSETS_PER_RUN`` above
        the new ceiling keeps working: the value is clamped and the run records
        ``max_assets`` in ``limits_hit`` when it stops. Raising here would break
        an existing installation on upgrade, which is not acceptable for a
        limit.
        """
        return cls(
            depth=DEFAULT_DEPTH,
            max_pages=DEFAULT_PAGES,
            max_assets=min(
                max(1, int(getattr(settings, "max_assets_per_run", DEFAULT_ASSETS))),
                MAX_ASSETS_CEILING,
            ),
            max_total_bytes=DEFAULT_TOTAL_BYTES,
            max_seconds=DEFAULT_SECONDS,
            max_concurrency=DEFAULT_CONCURRENCY,
        )

    def describe(self) -> dict[str, int | bool]:
        """JSON-safe snapshot persisted with the run and shown in Coverage."""
        return {
            "depth": self.depth,
            "max_pages": self.max_pages,
            "max_assets": self.max_assets,
            "max_total_bytes": self.max_total_bytes,
            "max_seconds": self.max_seconds,
            "max_concurrency": self.max_concurrency,
            "honor_robots": self.honor_robots,
        }


@dataclass(slots=True)
class BudgetTracker:
    """Mutable counters of one run against one :class:`CrawlBudget`.

    Every ``charge_*`` returns ``True`` when the charge was accepted and
    ``False`` when it would cross a limit — in which case the limit is recorded
    and the caller must stop. The asymmetry is intentional: a caller that
    ignores the return value keeps working (it just overshoots by one), so a
    missed check can never crash a run.
    """

    budget: CrawlBudget
    # Injectable so a test can simulate an elapsed budget without sleeping and
    # without freezing the process clock (which would also freeze the deadline).
    started_at: float = field(default_factory=time.monotonic)
    pages_crawled: int = 0
    assets_queued: int = 0
    bytes_downloaded: int = 0
    assets_processed: int = 0
    # Courtesy counters. ``robots_checked`` stays false until a robots.txt
    # read was actually attempted, so a run that stopped first does not claim
    # the file was consulted. Missing keys on an old snapshot mean the same.
    robots_checked: bool = False
    robots_omitted: int = 0
    sitemaps_ignored: int = 0
    sitemaps_truncated: bool = False
    _limits: list[str] = field(default_factory=list)

    # -- queries ----------------------------------------------------------

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    @property
    def limits_hit(self) -> tuple[str, ...]:
        """Limits actually reached, in the order they were hit (deduplicated)."""
        return tuple(self._limits)

    @property
    def exhausted(self) -> bool:
        """True when any limit is already reached: no further request is allowed."""
        return bool(self._limits)

    def _hit(self, limit: str) -> None:
        if limit not in self._limits:
            self._limits.append(limit)

    # -- charges ----------------------------------------------------------

    def charge_page(self) -> bool:
        """Account for crawling one more page."""
        if self.pages_crawled >= self.budget.max_pages:
            self._hit(LIMIT_PAGES)
            return False
        self.pages_crawled += 1
        return True

    def note_depth_limit(self) -> None:
        """Record that the crawl stopped at the configured depth."""
        self._hit(LIMIT_DEPTH)

    def note_asset_limit(self) -> None:
        """Record that the asset queue was truncated at the cap."""
        self._hit(LIMIT_ASSETS)

    def charge_asset(self) -> bool:
        """Account for queueing one more asset for download."""
        if self.assets_queued >= self.budget.max_assets:
            self._hit(LIMIT_ASSETS)
            return False
        self.assets_queued += 1
        return True

    def charge_bytes(self, count: int) -> bool:
        """Account for ``count`` downloaded bytes.

        The bytes are added even when the charge is refused: the transfer
        already happened, and under-reporting the traffic would be dishonest.
        """
        self.bytes_downloaded += max(0, count)
        if self.bytes_downloaded > self.budget.max_total_bytes:
            self._hit(LIMIT_BYTES)
            return False
        return True

    def check_deadline(self) -> bool:
        """False once the wall-clock budget is spent (recorded once)."""
        if self.elapsed_seconds >= self.budget.max_seconds:
            self._hit(LIMIT_SECONDS)
            return False
        return True

    # -- snapshot ---------------------------------------------------------

    def snapshot(self) -> dict[str, object]:
        """Persistable summary; the shape ``Run.ingestion_stats`` stores."""
        return {
            "budget": self.budget.describe(),
            "pages_crawled": self.pages_crawled,
            "assets_queued": self.assets_queued,
            "assets_processed": self.assets_processed,
            "bytes_downloaded": self.bytes_downloaded,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "limits_hit": list(self._limits),
            "robots_checked": self.robots_checked,
            "robots_omitted": self.robots_omitted,
            "sitemaps_ignored": self.sitemaps_ignored,
            "sitemaps_truncated": self.sitemaps_truncated,
        }
