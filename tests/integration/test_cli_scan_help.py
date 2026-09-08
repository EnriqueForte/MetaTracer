"""CLI smoke tests (TASK-06, subtask 6.2): help text and the scope gate.

CliRunner is not a TTY, so the interactive confirmation prompt aborts — which
is exactly the contracted behavior: without ``-y`` the scan never starts.
Every test points ``METATRACER_DATABASE_URL`` at a tmp_path so the real user
database is never touched.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metatracer.cli.main import app

runner = CliRunner()


def test_python_dash_m_entry_point_matches_readme() -> None:
    """README documents ``python -m metatracer``; the module must be executable."""
    completed = subprocess.run(
        [sys.executable, "-m", "metatracer", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "scan" in completed.stdout and "serve" in completed.stdout


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the database to tmp_path for every CLI test in this module."""
    monkeypatch.setenv("METATRACER_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cli-test.db")


def test_scan_help_lists_scope_option() -> None:
    result = runner.invoke(app, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--scope-domain" in result.output


def test_scan_without_scope_domain_fails() -> None:
    result = runner.invoke(app, ["scan", "target.com", "-y"])
    assert result.exit_code != 0
    assert "scope" in result.output.lower()


def test_scan_without_confirmation_aborts_in_non_tty() -> None:
    result = runner.invoke(app, ["scan", "target.com", "-s", "target.com"])
    assert result.exit_code != 0


def test_list_runs_empty_database() -> None:
    result = runner.invoke(app, ["list-runs"])
    assert result.exit_code == 0
    assert "no runs" in result.output.lower()


def test_list_runs_status_and_limit_flags() -> None:
    result = runner.invoke(app, ["list-runs", "--help"])
    assert result.exit_code == 0
    assert "--status" in result.output
    assert "--limit" in result.output


def test_show_help_lists_filters() -> None:
    result = runner.invoke(app, ["show", "--help"])
    assert result.exit_code == 0
    assert "--severity" in result.output
    assert "--type" in result.output


def test_show_unknown_run_fails() -> None:
    result = runner.invoke(app, ["show", "00000000-0000-0000-0000-000000000000"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_report_unknown_run_fails() -> None:
    result = runner.invoke(app, ["report", "00000000-0000-0000-0000-000000000000"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
