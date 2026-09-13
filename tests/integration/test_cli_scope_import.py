"""CLI scope import/export (TASK-19, v2.2): portable scopes from the terminal.

CliRunner is not a TTY, but ``scope import``/``scope export`` are
non-interactive (no confirmation gate), so they run to completion. Every test
points ``METATRACER_DATABASE_URL`` at a tmp_path so the real user database is
never touched.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metatracer.cli.main import app

runner = CliRunner()

_VALID = {
    "format_version": 1,
    "scopes": [
        {
            "name": "acme-2026",
            "description": "Acme Corp engagement",
            "domains": ["target.com", "*.target.com", "static.Target.com:8080"],
        }
    ],
}


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the database to tmp_path for every CLI test in this module."""
    monkeypatch.setenv(
        "METATRACER_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cli-scope-test.db"
    )


def test_scope_import_exit_zero_and_counts(tmp_path: Path) -> None:
    path = tmp_path / "scopes.json"
    path.write_text(json.dumps(_VALID), encoding="utf-8")
    result = runner.invoke(app, ["scope", "import", str(path)])
    assert result.exit_code == 0, result.output
    assert "Imported 1 scope(s)" in result.output
    assert "0 skipped" in result.output


def test_scope_import_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "scopes.json"
    path.write_text(json.dumps(_VALID), encoding="utf-8")
    first = runner.invoke(app, ["scope", "import", str(path)])
    second = runner.invoke(app, ["scope", "import", str(path)])
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Imported 1 scope(s)" in first.output
    assert "Imported 0 scope(s)" in second.output
    assert "1 skipped" in second.output


def test_scope_import_missing_file_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scope", "import", str(tmp_path / "nope.json")])
    assert result.exit_code != 0
    assert "file not found" in result.output.lower()


def test_scope_import_invalid_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"format_version": 99, "scopes": []}', encoding="utf-8")
    result = runner.invoke(app, ["scope", "import", str(path)])
    assert result.exit_code != 0
    assert "Import failed" in result.output
    assert "format_version" in result.output.lower()


def test_scope_export_round_trips(tmp_path: Path) -> None:
    # Import first, then export: the file carries only the contract fields.
    src = tmp_path / "in.json"
    src.write_text(json.dumps(_VALID), encoding="utf-8")
    imported = runner.invoke(app, ["scope", "import", str(src)])
    assert imported.exit_code == 0, imported.output

    out = tmp_path / "out.json"
    exported = runner.invoke(app, ["scope", "export", "--output", str(out)])
    assert exported.exit_code == 0, exported.output
    assert "Exported 1 scope" in exported.output

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format_version"] == 1
    assert len(payload["scopes"]) == 1
    entry = payload["scopes"][0]
    # Only the contract keys leave the machine.
    assert set(entry) == {"name", "description", "domains"}
    assert "id" not in entry
    assert "created_at" not in entry


def test_scope_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["scope", "--help"])
    assert result.exit_code == 0
    assert "import" in result.output