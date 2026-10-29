"""Crawl budget and tracker (Fase 2).

The budget is the mechanism that lets a run say *why* it stopped. These tests
pin three things:

1. Configuration is validated and clamped, never silently widened.
2. A charge that crosses a limit is refused **and recorded** — "reached" is
   evidence, not an inference.
3. The snapshot is JSON-safe and round-trips, because it is persisted on the
   run and read back by the coverage endpoint.

No network, no database: pure objects.
"""

import json

import pytest

from metatracer.core.config import Settings
from metatracer.extractors.budget import (
    DEFAULT_ASSETS,
    LIMIT_ASSETS,
    LIMIT_BYTES,
    LIMIT_DEPTH,
    LIMIT_PAGES,
    LIMIT_SECONDS,
    MAX_ASSETS_CEILING,
    BudgetTracker,
    CrawlBudget,
)


class TestCrawlBudget:
    def test_defaults_reproduce_the_historical_behaviour(self) -> None:
        budget = CrawlBudget()
        # One page and the configured asset cap: an unconfigured run is not
        # silently wider than before Fase 2.
        assert budget.depth == 1
        assert budget.max_pages == 1
        assert budget.max_assets == DEFAULT_ASSETS

    def test_rejects_a_value_below_the_floor(self) -> None:
        with pytest.raises(ValueError, match="depth must be >= 1"):
            CrawlBudget(depth=0)
        with pytest.raises(ValueError, match="max_assets must be >= 1"):
            CrawlBudget(max_assets=0)

    def test_rejects_a_value_above_the_ceiling(self) -> None:
        # A typo must not turn an audit into a scrape.
        with pytest.raises(ValueError, match="max_assets must be <="):
            CrawlBudget(max_assets=MAX_ASSETS_CEILING + 1)
        with pytest.raises(ValueError, match="depth must be <="):
            CrawlBudget(depth=99)

    def test_from_settings_clamps_instead_of_breaking_an_upgrade(self) -> None:
        # An installation with a huge METATRACER_MAX_ASSETS_PER_RUN keeps
        # working: the limit is clamped, not rejected.
        settings = Settings(_env_file=None, max_assets_per_run=100_000)
        budget = CrawlBudget.from_settings(settings)
        assert budget.max_assets == MAX_ASSETS_CEILING

    def test_from_settings_uses_the_existing_asset_cap(self) -> None:
        settings = Settings(_env_file=None, max_assets_per_run=12)
        assert CrawlBudget.from_settings(settings).max_assets == 12

    def test_describe_is_json_safe_and_complete(self) -> None:
        budget = CrawlBudget(depth=2, max_pages=5, max_assets=10, max_concurrency=4)
        described = budget.describe()
        assert described == {
            "depth": 2,
            "max_pages": 5,
            "max_assets": 10,
            "max_total_bytes": budget.max_total_bytes,
            "max_seconds": budget.max_seconds,
            "max_concurrency": 4,
            "honor_robots": True,
        }
        json.dumps(described)  # the snapshot must persist without a custom encoder


class TestBudgetTracker:
    def test_page_cap_is_refused_and_recorded(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(max_pages=2, max_assets=10))
        assert tracker.charge_page() is True
        assert tracker.charge_page() is True
        assert tracker.charge_page() is False
        assert tracker.pages_crawled == 2  # the refused charge did not count
        assert tracker.limits_hit == (LIMIT_PAGES,)
        assert tracker.exhausted is True

    def test_asset_cap_is_refused_and_recorded(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(max_pages=5, max_assets=2))
        assert tracker.charge_asset() is True
        assert tracker.charge_asset() is True
        assert tracker.charge_asset() is False
        assert tracker.assets_queued == 2
        assert tracker.limits_hit == (LIMIT_ASSETS,)

    def test_byte_cap_counts_the_transfer_even_when_refused(self) -> None:
        # The transfer already happened; under-reporting it would be dishonest.
        tracker = BudgetTracker(budget=CrawlBudget(max_total_bytes=100))
        assert tracker.charge_bytes(60) is True
        assert tracker.charge_bytes(60) is False
        assert tracker.bytes_downloaded == 120
        assert tracker.limits_hit == (LIMIT_BYTES,)

    def test_byte_cap_allows_exactly_the_limit(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(max_total_bytes=100))
        assert tracker.charge_bytes(100) is True
        assert tracker.limits_hit == ()

    def test_deadline_is_refused_and_recorded_once(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(max_seconds=1))
        # Pretend the run started long ago rather than sleeping.
        tracker.started_at -= 10
        assert tracker.check_deadline() is False
        assert tracker.check_deadline() is False
        assert tracker.limits_hit == (LIMIT_SECONDS,)  # deduplicated
        assert tracker.elapsed_seconds >= 1

    def test_limits_are_deduplicated_and_keep_the_order_hit(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(max_pages=1, max_assets=1, max_total_bytes=1))
        tracker.charge_page()
        tracker.charge_page()
        tracker.charge_asset()
        tracker.charge_asset()
        tracker.charge_bytes(10)
        assert tracker.limits_hit == (LIMIT_PAGES, LIMIT_ASSETS, LIMIT_BYTES)

    def test_note_depth_limit_is_explicit(self) -> None:
        # Depth is enforced by the crawler; recording it is separate because
        # stopping at the configured depth is a decision, not a counter.
        tracker = BudgetTracker(budget=CrawlBudget(depth=1))
        tracker.note_depth_limit()
        assert tracker.limits_hit == (LIMIT_DEPTH,)

    def test_snapshot_is_persistable_and_readable(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget(depth=2, max_pages=3, max_assets=7))
        tracker.charge_page()
        tracker.charge_asset()
        tracker.charge_bytes(2048)
        tracker.note_depth_limit()
        snapshot = tracker.snapshot()

        encoded = json.dumps(snapshot)
        decoded = json.loads(encoded)
        assert decoded["pages_crawled"] == 1
        assert decoded["assets_queued"] == 1
        assert decoded["bytes_downloaded"] == 2048
        assert decoded["limits_hit"] == [LIMIT_DEPTH]
        assert decoded["budget"]["depth"] == 2
        assert decoded["budget"]["max_assets"] == 7
        assert decoded["elapsed_seconds"] >= 0

    def test_a_fresh_tracker_reports_no_limits(self) -> None:
        tracker = BudgetTracker(budget=CrawlBudget())
        assert tracker.exhausted is False
        assert tracker.limits_hit == ()
        assert tracker.snapshot()["limits_hit"] == []
