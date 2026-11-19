"""Command line entry point for the Bridge-Agents server.

Usage::

    bridge-agents demo            # one command: mock model + API + built web UI
    bridge-agents serve           # serve the API (and the built UI when present)
    bridge-agents init-db         # create the database schema
    bridge-agents doctor          # check the local demo prerequisites
    bridge-agents version         # print package versions

The ``demo`` command is intentionally dependency-free: it starts the bundled
deterministic mock model, enables the demo login, and serves the built React UI
on the same port, so a fresh checkout only needs ``uv sync`` and Node for the
first web build.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_MOCK_PORT = 8001


def _repo_root() -> Path | None:
    """Return the checkout root when the CLI runs from a source tree."""
    candidates = [Path(__file__).resolve().parents[1], Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "app" / "main.py").is_file():
            return candidate
    return None


def _lan_address() -> str:
    """Best-effort local network address for the printed demo URL."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def _demo_environment(root: Path, mock_port: int) -> dict[str, str]:
    """Environment overrides that make a checkout run like the Docker demo."""
    return {
        "APP_ENV": "development",
        "ALLOW_DEV_LOGIN": "true",
        "ALLOWED_HOSTS": "*",
        "LLM_MODE": "mock",
        "OPENAI_BASE_URL": f"http://127.0.0.1:{mock_port}/v1",
        "WEB_DIST_DIR": str(root / "web" / "dist"),
    }


def _ensure_env_file(root: Path) -> Path | None:
    """Copy ``.env.example`` to ``.env`` on first run (never overwrite)."""
    env_file = root / ".env"
    if env_file.exists():
        return env_file
    example = root / ".env.example"
    if not example.is_file():
        return None
    shutil.copyfile(example, env_file)
    return env_file


def _ensure_web_build(root: Path, *, build: bool) -> bool:
    """Build the web UI when it is missing and Node is available."""
    index = root / "web" / "dist" / "index.html"
    if index.is_file():
        return True
    if not build:
        print("! web UI is not built; the API will start without the browser UI.")
        return False
    npm = shutil.which("npm")
    if npm is None:
        print("! web UI is not built and npm was not found; starting without the browser UI.")
        print("  Install Node.js and run `npm --prefix web install && npm --prefix web run build`.")
        return False
    print("Building the web UI for the first demo run (this can take a minute)...")
    result = subprocess.run([npm, "run", "build"], cwd=root / "web", check=False)
    if result.returncode != 0 or not index.is_file():
        print("! web build failed; the API will start without the browser UI.")
        return False
    return True


def _start_mock(root: Path, port: int) -> subprocess.Popen | None:
    """Start the bundled mock model when this checkout ships one."""
    if not (root / "mock" / "main.py").is_file():
        return None
    print(f"Starting the deterministic mock model on 127.0.0.1:{port} ...")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mock.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=root,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit("mock model exited before it became ready")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                if response.status == 200:
                    return process
        except OSError:
            time.sleep(0.25)
    process.terminate()
    raise SystemExit("mock model did not become ready within 20 seconds")


def _print_demo_urls(host: str, port: int) -> None:
    lan = _lan_address()
    print("")
    print("Bridge-Agents demo is ready:")
    print(f"  Customer UI:   http://localhost:{port}/")
    print(f"  Support desk:  http://localhost:{port}/admin")
    print(f"  API health:    http://localhost:{port}/health")
    if host == "0.0.0.0" and lan not in ("127.0.0.1", ""):
        print(f"  From your LAN: http://{lan}:{port}/")
    print("  Demo login is enabled (no password); press Ctrl+C to stop.")
    print("")


def _command_demo(args: argparse.Namespace) -> int:
    root = _repo_root()
    if root is None:
        print("`bridge-agents demo` must run from the Bridge-Agents source checkout.")
        print("Install the app inside a checkout, or use `docker compose up --build`.")
        return 2
    created = _ensure_env_file(root)
    if created is not None:
        print(f"Created {created} from .env.example for the demo.")
    os.environ.update(_demo_environment(root, args.mock_port))
    _ensure_web_build(root, build=not args.no_build)
    mock = _start_mock(root, args.mock_port)
    _print_demo_urls(args.host, args.port)
    try:
        import uvicorn

        uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        if mock is not None:
            mock.terminate()
            try:
                mock.wait(timeout=10)
            except subprocess.TimeoutExpired:
                mock.kill()
    return 0


def _command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _command_init_db() -> int:
    import asyncio

    from app.models.database import dispose_engine, init_db

    async def run() -> None:
        await init_db()
        await dispose_engine()

    asyncio.run(run())
    print("Database schema is ready.")
    return 0


def _command_version() -> int:
    versions: dict[str, str] = {}
    for package in ("bridge-agents-app", "bridge-agents"):
        try:
            versions[package] = distribution_version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    print(f"Python {sys.version.split()[0]}")
    for package, version in versions.items():
        print(f"{package} {version}")
    return 0


def _command_doctor() -> int:
    root = _repo_root()
    print("Bridge-Agents doctor")
    print(f"  Python:        {sys.version.split()[0]}")
    print(f"  Checkout:      {root or 'not detected'}")
    if root is None:
        return 0
    env_file = root / ".env"
    print(f"  .env:          {'present' if env_file.is_file() else 'missing (demo creates it)'}")
    web_index = root / "web" / "dist" / "index.html"
    print(f"  Web UI build:  {'present' if web_index.is_file() else 'missing'}")
    mock = root / "mock" / "main.py"
    print(f"  Mock model:    {'present' if mock.is_file() else 'missing'}")
    print(f"  npm:           {shutil.which('npm') or 'not found'}")
    for port in (8000, 8001):
        busy = _port_in_use(port)
        print(f"  Port {port}:      {'in use' if busy else 'free'}")
    return 0


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridge-agents",
        description="Bridge-Agents server: demo, serve and maintenance commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="serve the API and built web UI")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--reload", action="store_true", help="reload on Python changes")
    serve.set_defaults(handler=_command_serve)

    demo = subparsers.add_parser("demo", help="one-command local demo (mock model + API + UI)")
    demo.add_argument("--host", default=DEFAULT_HOST)
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.add_argument("--mock-port", type=int, default=DEFAULT_MOCK_PORT)
    demo.add_argument("--no-build", action="store_true", help="never build the web UI")
    demo.set_defaults(handler=_command_demo)

    init_db = subparsers.add_parser("init-db", help="create the database schema")
    init_db.set_defaults(handler=lambda _args: _command_init_db())

    version = subparsers.add_parser("version", help="print package versions")
    version.set_defaults(handler=lambda _args: _command_version())

    doctor = subparsers.add_parser("doctor", help="check the local demo prerequisites")
    doctor.set_defaults(handler=lambda _args: _command_doctor())
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    return int(handler(args))


if __name__ == "__main__":  # pragma: no cover - console-script fallback
    raise SystemExit(main())
