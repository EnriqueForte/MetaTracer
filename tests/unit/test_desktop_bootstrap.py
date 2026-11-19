"""TASK-56: clone installer and app launcher (stdlib scripts/desktop.py)."""

from __future__ import annotations

import importlib.util
import os
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "desktop.py"


def load_desktop():
    spec = importlib.util.spec_from_file_location("mt_desktop", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def desktop():
    return load_desktop()


def test_python_version_gate(desktop) -> None:
    assert desktop.python_supported((3, 11, 0)) is True
    assert desktop.python_supported((3, 12, 9)) is True
    assert desktop.python_supported((3, 10, 14)) is False
    assert desktop.python_supported((3, 13, 0)) is False
    assert desktop.python_supported((4, 0, 0)) is False


def test_node_version_gate(desktop) -> None:
    assert desktop.node_supported("v20.0.0") is True
    assert desktop.node_supported("v24.11.0") is True
    assert desktop.node_supported("v18.20.0") is False
    with pytest.raises(desktop.BootstrapError):
        desktop.parse_node_major("not-a-version")


def test_child_env_strips_loopback_flag(desktop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(desktop.LOOPBACK_FLAG, "true")
    env = desktop.child_env()
    assert desktop.LOOPBACK_FLAG not in env
    # Parent process is unchanged; we only scrub children.
    assert os.environ.get(desktop.LOOPBACK_FLAG) == "true"


def test_venv_python_path_matches_platform(
    desktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desktop.os, "name", "nt")
    assert desktop.venv_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"
    monkeypatch.setattr(desktop.os, "name", "posix")
    assert desktop.venv_python(tmp_path) == tmp_path / ".venv" / "bin" / "python"


def test_ensure_env_file_copies_and_does_not_overwrite(desktop, tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("METATRACER_LOG_LEVEL=INFO\n", encoding="utf-8")
    dest = desktop.ensure_env_file(tmp_path)
    assert dest.read_text(encoding="utf-8") == "METATRACER_LOG_LEVEL=INFO\n"
    dest.write_text("METATRACER_LOG_LEVEL=DEBUG\n", encoding="utf-8")
    again = desktop.ensure_env_file(tmp_path)
    assert again.read_text(encoding="utf-8") == "METATRACER_LOG_LEVEL=DEBUG\n"


def test_copied_env_does_not_enable_loopback() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "METATRACER_ALLOW_LOOPBACK=false" in example
    assert "METATRACER_ALLOW_LOOPBACK=true" not in example


def test_run_refuses_missing_venv_without_spawning(
    desktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[object] = []

    def _should_not_run(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("Popen must not run when install is incomplete")

    monkeypatch.setattr(desktop.subprocess, "Popen", _should_not_run)
    with pytest.raises(desktop.BootstrapError, match="install"):
        desktop.run(tmp_path, open_browser=False)
    assert spawned == []


def test_run_refuses_missing_node_modules(
    desktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_py = desktop.venv_python(tmp_path)
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("", encoding="utf-8")
    spawned: list[object] = []

    def _should_not_run(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("Popen must not run when node_modules is missing")

    monkeypatch.setattr(desktop.subprocess, "Popen", _should_not_run)
    with pytest.raises(desktop.BootstrapError, match="node_modules"):
        desktop.run(tmp_path, open_browser=False)
    assert spawned == []


def test_install_pip_and_npm_commands(
    desktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        assert desktop.LOOPBACK_FLAG not in env
        calls.append(list(argv))

    monkeypatch.setattr(desktop, "python_supported", lambda _info: True)
    monkeypatch.setattr(desktop, "require_node", lambda: ("node", "npm.cmd"))
    monkeypatch.setattr(desktop, "read_node_version", lambda _exe: "v24.0.0")
    monkeypatch.setattr(desktop, "create_venv", lambda root, recreate=False: tmp_path / "python")
    monkeypatch.setattr(desktop, "run_command", fake_run)
    monkeypatch.setattr(desktop, "write_linux_desktop_entry", lambda root: None)
    (tmp_path / ".env.example").write_text("METATRACER_LOG_LEVEL=INFO\n", encoding="utf-8")

    desktop.install(tmp_path)
    pip_editable = [
        cmd
        for cmd in calls
        if cmd[:4] == [str(tmp_path / "python"), "-m", "pip", "install"]
        and "-e" in cmd
        and cmd[-1] == "."
    ]
    assert pip_editable
    assert any(cmd == ["npm.cmd", "ci"] for cmd in calls)

    calls.clear()
    desktop.install(tmp_path, dev=True)
    assert any(cmd[-1] == ".[dev]" and "-e" in cmd for cmd in calls)


def test_hints_cover_windows_and_parrot(desktop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop.os, "name", "nt")
    assert "winget" in desktop.python_hint()
    assert "winget" in desktop.node_hint()
    assert "MetaTracer.cmd" in desktop.launcher_hint()
    monkeypatch.setattr(desktop.os, "name", "posix")
    assert "apt install" in desktop.python_hint()
    assert "Parrot" in desktop.python_hint() or "apt" in desktop.node_hint()
    assert "run.sh" in desktop.launcher_hint()


def test_wait_for_port_accepts_open_listener(desktop) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _accept() -> None:
        conn, _addr = server.accept()
        conn.close()

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    desktop.wait_for_port(port, timeout_s=2.0)
    server.close()
    thread.join(timeout=1)


def test_wait_for_port_times_out(desktop) -> None:
    with pytest.raises(desktop.BootstrapError, match="Timed out"):
        desktop.wait_for_port(1, host="127.0.0.1", timeout_s=0.3)


def test_linux_desktop_entry_points_at_run_sh(
    desktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desktop.os, "name", "posix")
    (tmp_path / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    (tmp_path / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    path = desktop.write_linux_desktop_entry(tmp_path)
    assert path is not None
    body = path.read_text(encoding="utf-8")
    assert f"Exec={tmp_path / 'run.sh'}" in body
    assert f"Path={tmp_path}" in body
    assert "Terminal=true" in body


def test_wrappers_exist_with_expected_entrypoints() -> None:
    install_sh = (ROOT / "install.sh").read_bytes()
    run_sh = (ROOT / "run.sh").read_bytes()
    assert install_sh.startswith(b"#!/usr/bin/env bash\n")
    assert run_sh.startswith(b"#!/usr/bin/env bash\n")
    assert b"\r" not in install_sh
    assert b"\r" not in run_sh
    assert b"scripts/desktop.py" in install_sh
    assert b"scripts/desktop.py" in run_sh
    install_cmd = (ROOT / "install.cmd").read_text(encoding="utf-8")
    app_cmd = (ROOT / "MetaTracer.cmd").read_text(encoding="utf-8")
    assert "desktop.py" in install_cmd
    assert "install" in install_cmd
    assert "desktop.py" in app_cmd
    assert "run %" in app_cmd
