"""TASK-44: UTC 5-field crontab for watch --cron (stdlib, no apscheduler)."""

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from metatracer.cli.main import app
from metatracer.services.cron import CronError, next_fire, parse_cron, seconds_until


def test_parse_daily_alias_and_five_fields() -> None:
    daily = parse_cron("@daily")
    assert daily.minute == frozenset({0})
    assert daily.hour == frozenset({0})
    assert parse_cron("0 2 * * *").hour == frozenset({2})


def test_parse_lists_ranges_and_steps() -> None:
    schedule = parse_cron("*/15 9-17 * * 1-5")
    assert schedule.minute == frozenset({0, 15, 30, 45})
    assert 9 in schedule.hour and 17 in schedule.hour
    assert 0 not in schedule.weekday
    assert 1 in schedule.weekday and 5 in schedule.weekday


def test_sunday_seven_and_names() -> None:
    assert parse_cron("0 0 * * 7").weekday == frozenset({0})
    assert parse_cron("0 0 * jan mon").month == frozenset({1})
    assert parse_cron("0 0 * * mon").weekday == frozenset({1})


def test_invalid_expressions() -> None:
    with pytest.raises(CronError):
        parse_cron("")
    with pytest.raises(CronError):
        parse_cron("* * *")
    with pytest.raises(CronError):
        parse_cron("60 0 * * *")
    with pytest.raises(CronError):
        parse_cron("0 0 32 * *")


def test_next_fire_is_utc_and_strictly_after() -> None:
    schedule = parse_cron("0 2 * * *")
    after = datetime(2026, 11, 5, 23, 0, tzinfo=UTC)
    fire = next_fire(schedule, after)
    assert fire == datetime(2026, 11, 6, 2, 0, tzinfo=UTC)


def test_next_fire_step_minutes() -> None:
    schedule = parse_cron("*/15 * * * *")
    after = datetime(2026, 11, 5, 10, 7, tzinfo=UTC)
    assert next_fire(schedule, after) == datetime(2026, 11, 5, 10, 15, tzinfo=UTC)


def test_impossible_date_raises() -> None:
    schedule = parse_cron("0 0 31 2 *")
    with pytest.raises(CronError, match="366"):
        next_fire(schedule, datetime(2026, 1, 1, tzinfo=UTC))


def test_seconds_until_at_least_one() -> None:
    schedule = parse_cron("* * * * *")
    now = datetime(2026, 11, 5, 10, 0, 0, tzinfo=UTC)
    assert seconds_until(schedule, now) == 60.0


def test_weekday_monday_cron_one() -> None:
    # 2026-11-09 is a Monday. Cron weekday 1 = Monday.
    schedule = parse_cron("0 0 * * 1")
    after = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)  # Sunday
    assert next_fire(schedule, after) == datetime(2026, 11, 9, 0, 0, tzinfo=UTC)


def test_watch_help_lists_cron() -> None:
    result = CliRunner().invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    assert "--cron" in result.output
    assert "--interval" in result.output


def test_watch_rejects_cron_with_interval() -> None:
    result = CliRunner().invoke(
        app, ["watch", "scope-id", "--cron", "0 2 * * *", "--interval", "60"]
    )
    assert result.exit_code != 0
    assert "--cron cannot be combined with --interval" in result.output


def test_watch_rejects_cron_with_once() -> None:
    result = CliRunner().invoke(app, ["watch", "scope-id", "--once", "--cron", "0 2 * * *"])
    assert result.exit_code != 0
    assert "--once cannot be combined with --cron" in result.output


def test_watch_rejects_malformed_cron() -> None:
    result = CliRunner().invoke(app, ["watch", "scope-id", "--cron", "not-a-cron"])
    assert result.exit_code != 0
    assert "5 fields" in result.output
