"""Package the built web UI as a versioned release artifact.

The Python packages intentionally exclude the GUI. Releases attach this static
archive next to the wheels so it can be deployed by nginx/CDN independently.

Usage:
    uv run python scripts/package_web.py
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from bridge_agents import __version__ as version
except ImportError:  # pragma: no cover - run without the package installed
    version = "0.1.0"


def main() -> int:
    dist = PROJECT_ROOT / "web" / "dist"
    if not (dist / "index.html").is_file():
        print("web/dist is missing; run `npm --prefix web run build` first.")
        return 1
    output_dir = PROJECT_ROOT / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"bridge-agents-web-{version}.tar.gz"
    root_name = f"bridge-agents-web-{version}"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dist, arcname=f"{root_name}/web")
        readme = PROJECT_ROOT / "deploy" / "nginx.conf"
        if readme.is_file():
            tar.add(readme, arcname=f"{root_name}/nginx.conf")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
