"""CLI watch command smoke tests (TASK-22, v3.0 Eje A).

The watch command reuses the exact pipeline, so these tests only verify the
CLI shell: help text, the scope gate, ``--once`` aborting on a missing scope
and the per-scope lock refusing a second concurrent watcher.
"""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metatracer.cli.main import _release_scope_lock, _scope_lock, app

runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Strip ANSI colour codes (Rich/Typer behaviour differs on Windows/Linux)."""
    return _ANSI_RE.sub("", output)


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real user database while exercising the CLI shell."""
    monkeypatch.setenv(
        "METATRACER_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/watch-cli-test.db"
    )


def test_watch_help_lists_scope_and_once() -> None:
    result = runner.invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    output = _plain(result.output)
    assert "--once" in output
    assert "--interval" in output


def test_watch_once_without_scope_aborts() -> None:
    result = runner.invoke(app, ["watch", "--once", "not-a-real-scope"])
    assert result.exit_code != 0
    assert "scope not found" in result.output.lower()


def test_watch_scope_lock_refuses_second_watcher(tmp_path: Path) -> None:
    scope_id = f"locked-scope-{Path(tmp_path).name}"
    first = _scope_lock(scope_id)
    assert first is not None
    try:
        second = _scope_lock(scope_id)
        assert second is None
    finally:
        _release_scope_lock(first)