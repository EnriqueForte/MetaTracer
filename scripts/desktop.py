"""Clone installer and app launcher for Windows and Linux (TASK-56).

Stdlib only. This file is executed *before* the MetaTracer package is
installed, so it must not import ``metatracer``. It never sets
``METATRACER_ALLOW_LOOPBACK`` and strips that flag from child processes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from collections.abc import Callable
from pathlib import Path

MIN_PY = (3, 11)
MAX_PY_EXCLUSIVE = (3, 13)
MIN_NODE_MAJOR = 20
LOOPBACK_FLAG = "METATRACER_ALLOW_LOOPBACK"
AUTH_FLAG = "METATRACER_AUTH_ENABLED"
APP_URL = "http://127.0.0.1:3000"
LOGIN_URL = f"{APP_URL}/login"
WEB_PORT = 3000
WEB_WAIT_SECONDS = 120.0

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPTS_DIR.parent


class BootstrapError(Exception):
    """User-facing installer/launcher failure."""


def python_supported(version_info: tuple[int, ...] | sys.version_info) -> bool:
    pair = (int(version_info[0]), int(version_info[1]))
    return MIN_PY <= pair < MAX_PY_EXCLUSIVE


def parse_node_major(version: str) -> int:
    text = version.strip()
    if text.startswith(("v", "V")):
        text = text[1:]
    major = text.split(".", 1)[0]
    if not major.isdigit():
        raise BootstrapError(f"Could not parse Node.js version: {version!r}")
    return int(major)


def node_supported(version: str) -> bool:
    return parse_node_major(version) >= MIN_NODE_MAJOR


def child_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for pip/npm/serve: inherit the host, drop the test-only flag."""
    env = dict(os.environ if base is None else base)
    env.pop(LOOPBACK_FLAG, None)
    return env


def launch_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Runtime env for ``./run.sh`` / MetaTracer.cmd.

    Auth is ON so a clone hits /login and first-user setup. The Settings
    default stays false for pytest and a bare ``metatracer serve``. An
    explicit ``METATRACER_AUTH_ENABLED`` in the process environment wins
    (including ``false``). A ``false`` only in ``.env`` does not: the
    child env var overrides the file.
    """
    env = child_env(base)
    if AUTH_FLAG not in env:
        env[AUTH_FLAG] = "true"
    return env


def venv_dir(root: Path) -> Path:
    return root / ".venv"


def venv_python(root: Path) -> Path:
    if os.name == "nt":
        return venv_dir(root) / "Scripts" / "python.exe"
    return venv_dir(root) / "bin" / "python"


def web_root(root: Path) -> Path:
    return root / "web"


def node_modules_dir(root: Path) -> Path:
    return web_root(root) / "node_modules"


def venv_apt_package(version_info: tuple[int, ...] | sys.version_info | None = None) -> str:
    info = sys.version_info if version_info is None else version_info
    return f"python{int(info[0])}.{int(info[1])}-venv"


def debian_venv_hint(version_info: tuple[int, ...] | sys.version_info | None = None) -> str:
    pkg = venv_apt_package(version_info)
    return (
        f"Debian/Parrot: sudo apt install {pkg} python3-pip\n"
        "Then: rm -rf .venv && ./install.sh"
    )


def venv_create_hint(version_info: tuple[int, ...] | sys.version_info | None = None) -> str:
    if os.name == "nt":
        return "Windows: repair the Python 3.11/3.12 install and include pip/venv."
    return debian_venv_hint(version_info)


def python_hint() -> str:
    if os.name == "nt":
        return "Install Python 3.11 or 3.12: winget install Python.Python.3.12"
    return (
        "Debian/Parrot: sudo apt install python3.11 python3.11-venv "
        "python3.12 python3.12-venv python3-pip\n"
        "Then rerun: ./install.sh"
    )


def node_hint() -> str:
    if os.name == "nt":
        return "Install Node.js 20 or newer: winget install OpenJS.NodeJS.LTS"
    return "Debian/Parrot: sudo apt install nodejs npm"


def launcher_hint() -> str:
    if os.name == "nt":
        return "Start the app: double-click MetaTracer.cmd (or run it from this folder)"
    return "Start the app: ./run.sh"


def _python_at_is_supported(exe: str) -> bool:
    try:
        proc = subprocess.run(
            [exe, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=child_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    parts = proc.stdout.strip().split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return False
    return python_supported((int(parts[0]), int(parts[1])))


def discover_python() -> str:
    if python_supported(sys.version_info):
        return sys.executable
    names = ("python3.12", "python3.11", "python3", "python")
    for name in names:
        path = shutil.which(name)
        if path and path != sys.executable and _python_at_is_supported(path):
            return path
    raise BootstrapError(
        "MetaTracer needs Python 3.11 or 3.12 (3.13+ is not supported).\n" + python_hint()
    )


def reexec_if_needed() -> None:
    """If this interpreter is 3.13+, hop to a supported one before creating the venv."""
    if python_supported(sys.version_info):
        return
    target = discover_python()
    os.execv(target, [target, *sys.argv])


def discover_node() -> str:
    path = shutil.which("node")
    if not path:
        raise BootstrapError("Node.js 20 or newer is required (Next.js Web UI).\n" + node_hint())
    return path


def discover_npm() -> str:
    path = shutil.which("npm")
    if not path:
        raise BootstrapError("npm is required to install the Web UI.\n" + node_hint())
    return path


def read_node_version(node_exe: str) -> str:
    try:
        proc = subprocess.run(
            [node_exe, "-v"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=child_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"Could not run {node_exe!r}: {exc}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise BootstrapError(f"node -v failed: {err or proc.returncode}")
    return proc.stdout.strip() or proc.stderr.strip()


def require_node() -> tuple[str, str]:
    node_exe = discover_node()
    version = read_node_version(node_exe)
    if not node_supported(version):
        raise BootstrapError(
            f"Node.js {version} is too old (need {MIN_NODE_MAJOR}+).\n" + node_hint()
        )
    npm_exe = discover_npm()
    return node_exe, npm_exe


def run_command(argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    printable = " ".join(argv)
    print(f"==> {printable}")
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def ensure_env_file(root: Path) -> Path:
    dest = root / ".env"
    if dest.exists():
        return dest
    src = root / ".env.example"
    if not src.is_file():
        raise BootstrapError(f"Missing {src.name}; clone looks incomplete.")
    dest.write_bytes(src.read_bytes())
    return dest


def ensure_runtime_dirs(root: Path) -> None:
    (root / "data").mkdir(exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)


def missing_install_markers(root: Path) -> list[str]:
    missing: list[str] = []
    if not venv_python(root).is_file():
        missing.append("Python virtualenv (.venv)")
    if not node_modules_dir(root).is_dir():
        missing.append("Web UI dependencies (web/node_modules)")
    return missing


def bootstrap_pip(interpreter: Path, root: Path) -> None:
    """Install pip into a venv created without ensurepip (Debian/Parrot)."""
    env = child_env()
    try:
        run_command(
            [sys.executable, "-m", "pip", "install", "--python", str(interpreter), "pip"],
            cwd=root,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise BootstrapError(
            "Could not bootstrap pip inside .venv (ensurepip is missing).\n" + venv_create_hint()
        ) from exc


def create_venv(root: Path, *, recreate: bool = False) -> Path:
    directory = venv_dir(root)
    interpreter = venv_python(root)
    if recreate and directory.exists():
        shutil.rmtree(directory)
    if interpreter.is_file():
        return interpreter
    print(f"==> Creating virtualenv at {directory}")
    try:
        venv.create(directory, with_pip=True)
    except Exception as first:
        if directory.exists():
            shutil.rmtree(directory)
        print("==> ensurepip missing; retrying without it")
        try:
            venv.create(directory, with_pip=False)
            if not interpreter.is_file():
                raise RuntimeError(f"missing {interpreter}")
            bootstrap_pip(interpreter, root)
        except Exception as second:
            if directory.exists():
                shutil.rmtree(directory)
            raise BootstrapError(
                f"Could not create .venv ({first}).\n{venv_create_hint()}"
            ) from second
    if not interpreter.is_file():
        raise BootstrapError(f"Virtualenv is missing {interpreter}")
    return interpreter


def pip_install(python: Path, root: Path, *, dev: bool = False) -> None:
    env = child_env()
    run_command([str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=root, env=env)
    spec = ".[dev]" if dev else "."
    run_command([str(python), "-m", "pip", "install", "-e", spec], cwd=root, env=env)


def npm_ci(npm_exe: str, root: Path) -> None:
    env = child_env()
    run_command([npm_exe, "ci"], cwd=web_root(root), env=env)


def write_linux_desktop_entry(root: Path) -> Path | None:
    if os.name == "nt":
        return None
    run_path = root / "run.sh"
    install_path = root / "install.sh"
    for script in (run_path, install_path):
        if script.is_file():
            script.chmod(script.stat().st_mode | 0o111)
    desktop = root / "MetaTracer.desktop"
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=MetaTracer\n"
        "Comment=Authorized sensitive-metadata discovery\n"
        f"Exec={run_path}\n"
        f"Path={root}\n"
        "Terminal=true\n"
        "Categories=Security;\n"
    )
    desktop.write_text(body, encoding="utf-8", newline="\n")
    desktop.chmod(desktop.stat().st_mode | 0o111)
    return desktop


def install(root: Path, *, dev: bool = False, recreate_venv: bool = False) -> None:
    print("MetaTracer installer")
    print(f"  repo  {root}")
    if not python_supported(sys.version_info):
        raise BootstrapError(
            "MetaTracer needs Python 3.11 or 3.12 (3.13+ is not supported).\n" + python_hint()
        )
    print(f"  python {sys.version.split()[0]} ({sys.executable})")
    node_exe, npm_exe = require_node()
    print(f"  node   {read_node_version(node_exe)}")
    interpreter = create_venv(root, recreate=recreate_venv)
    pip_install(interpreter, root, dev=dev)
    npm_ci(npm_exe, root)
    ensure_env_file(root)
    ensure_runtime_dirs(root)
    write_linux_desktop_entry(root)
    print("")
    print("Install finished.")
    print(f"  {launcher_hint()}")
    print(f"  UI: {APP_URL}   API: http://127.0.0.1:8000")


def wait_for_port(
    port: int,
    host: str = "127.0.0.1",
    timeout_s: float = WEB_WAIT_SECONDS,
    abort: Callable[[], bool] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        if abort is not None and abort():
            raise BootstrapError("stopped")
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            if abort is not None and abort():
                raise BootstrapError("stopped") from None
            if time.monotonic() >= deadline:
                raise BootstrapError(
                    f"Timed out waiting for {host}:{port}. Check the console output above."
                ) from None
            time.sleep(0.2)


def stop_process_posix(proc: subprocess.Popen[bytes]) -> None:
    """SIGTERM (then SIGKILL) the child's process group, not just npm."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            proc.kill()
        proc.wait(timeout=5)


def stop_process_windows(proc: subprocess.Popen[bytes]) -> None:
    """Kill npm and its grandchildren (Next + uvicorn)."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
        capture_output=True,
        check=False,
    )
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        stop_process_windows(proc)
        return
    stop_process_posix(proc)


def run(root: Path, *, open_browser: bool = True) -> int:
    missing = missing_install_markers(root)
    if missing:
        raise BootstrapError(
            "Run the installer first ("
            + ("install.cmd" if os.name == "nt" else "./install.sh")
            + "). Missing: "
            + ", ".join(missing)
        )
    npm_exe = discover_npm()
    env = launch_env()
    env["METATRACER_PYTHON"] = str(venv_python(root))
    print("MetaTracer")
    print("  API   http://127.0.0.1:8000")
    print(f"  App   {APP_URL}")
    print(f"  Login {LOGIN_URL}")
    print("  Auth is ON. First clone: create the operator at /setup")
    print("  (SETUP MODE token is printed once in the API log).")
    print("  Ctrl+C stops both processes.")
    if os.name == "nt":
        proc = subprocess.Popen(
            [npm_exe, "run", "dev"],
            cwd=web_root(root),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        proc = subprocess.Popen(
            [npm_exe, "run", "dev"],
            cwd=web_root(root),
            env=env,
            start_new_session=True,
        )
    stopping = False

    def _stop(_signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\nStopping MetaTracer.")
        stop_process(proc)

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    try:
        wait_for_port(WEB_PORT, abort=lambda: stopping)
        if stopping:
            return 130
        if open_browser:
            webbrowser.open(LOGIN_URL)
        code = int(proc.wait())
        return 130 if stopping else code
    except KeyboardInterrupt:
        _stop()
        return 130
    except BootstrapError as exc:
        if stopping or str(exc) == "stopped":
            _stop()
            return 130
        _stop()
        raise
    except Exception:
        _stop()
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install or launch MetaTracer after a git clone.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    install_p = sub.add_parser("install", help="Create .venv, install Python + Web UI")
    install_p.add_argument(
        "--dev",
        action="store_true",
        help="Also install pytest/ruff (contributor extra).",
    )
    install_p.add_argument(
        "--recreate-venv",
        action="store_true",
        help="Delete .venv and create it again.",
    )
    run_p = sub.add_parser("run", help="Start the API and Web UI")
    run_p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the default browser.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        reexec_if_needed()
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install(REPO_ROOT, dev=args.dev, recreate_venv=args.recreate_venv)
            return 0
        if args.command == "run":
            return run(REPO_ROOT, open_browser=not args.no_browser)
    except BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
