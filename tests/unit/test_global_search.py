"""TASK-46: ILIKE escaping and CLI help for global search."""

from typer.testing import CliRunner

from metatracer.cli.main import app
from metatracer.db.repositories import _like_needle


def test_like_needle_escapes_wildcards() -> None:
    assert _like_needle("100%") == r"%100\%%"
    assert _like_needle("a_b") == r"%a\_b%"
    assert _like_needle(r"c:\temp") == r"%c:\\temp%"


def test_search_cli_help() -> None:
    result = CliRunner().invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "persisted findings" in result.stdout.lower() or "Search persisted" in result.stdout
