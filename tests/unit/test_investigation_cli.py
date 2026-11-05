"""CLI investigation group (TASK-36): paridad mínima con el API, sin copiar triage."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metatracer.cli.main import app
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Run, RunStatus

runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    return _ANSI_RE.sub("", output)


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "investigation-cli.db"
    monkeypatch.setenv("METATRACER_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    return db_path


def _seed_run(db_path: Path) -> str:
    async def _go() -> str:
        engine = create_db_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            await init_db(engine)
            factory = create_session_factory(engine)
            async with factory() as session:
                run = Run(
                    target_input='["https://acme.com"]',
                    allowed_scope='["acme.com"]',
                    scope_confirmed=True,
                    status=RunStatus.completed,
                )
                session.add(run)
                await session.commit()
                await session.refresh(run)
                return run.id
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_investigation_help_lists_commands() -> None:
    result = runner.invoke(app, ["investigation", "--help"])
    assert result.exit_code == 0
    output = _plain(result.output)
    for name in ("list", "show", "create", "close", "attach", "detach"):
        assert name in output


def test_investigation_create_list_attach_show_close_refuses_attach(tmp_path: Path) -> None:
    db_path = tmp_path / "investigation-cli.db"
    run_id = _seed_run(db_path)

    created = runner.invoke(app, ["investigation", "create", "Acme 2026"])
    assert created.exit_code == 0, created.output
    assert "Created investigation" in created.output
    investigation_id = _plain(created.output).split()[2]

    listed = runner.invoke(app, ["investigation", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Acme 2026" in listed.output
    assert "open" in listed.output

    attached = runner.invoke(app, ["investigation", "attach", investigation_id, run_id])
    assert attached.exit_code == 0, attached.output

    shown = runner.invoke(app, ["investigation", "show", investigation_id])
    assert shown.exit_code == 0, shown.output
    assert "Acme 2026" in shown.output
    assert "1 run" in shown.output

    closed = runner.invoke(app, ["investigation", "close", investigation_id])
    assert closed.exit_code == 0, closed.output

    other_id = _seed_run(db_path)
    refused = runner.invoke(app, ["investigation", "attach", investigation_id, other_id])
    assert refused.exit_code == 1
    assert "closed investigation" in refused.output.lower()

    detached = runner.invoke(app, ["investigation", "detach", investigation_id, run_id])
    assert detached.exit_code == 0, detached.output


def test_investigation_duplicate_name_exits_one() -> None:
    first = runner.invoke(app, ["investigation", "create", "Same"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["investigation", "create", "Same"])
    assert second.exit_code == 1
    assert "already exists" in second.output.lower()


def test_investigation_show_missing_exits_one() -> None:
    result = runner.invoke(app, ["investigation", "show", "00000000-0000-4000-8000-000000000000"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
