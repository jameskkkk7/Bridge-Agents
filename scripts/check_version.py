"""Fail when the shipped version numbers disagree or a release tag is wrong.

Run locally with ``make version-check`` or in CI before publishing::

    python scripts/check_version.py
    python scripts/check_version.py --tag v0.1.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version(path: Path) -> str:
    with path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _module_version(path: Path) -> str:
    match = re.search(r'^__version__ = "([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"no __version__ found in {path}")
    return match.group(1)


def _changelog_versions(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)


def collect_versions() -> dict[str, str]:
    """Return every place the release version must agree."""
    return {
        "server: pyproject.toml": _pyproject_version(ROOT / "pyproject.toml"),
        "core: packages/bridge_agents/pyproject.toml": _pyproject_version(
            ROOT / "packages" / "bridge_agents" / "pyproject.toml"
        ),
        "core: bridge_agents.__version__": _module_version(
            ROOT / "packages" / "bridge_agents" / "src" / "bridge_agents" / "__init__.py"
        ),
        "web: package.json": str(
            json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))["version"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Bridge-Agents release versions.")
    parser.add_argument("--tag", default="", help="release tag to validate, e.g. v0.1.0")
    args = parser.parse_args(argv)

    versions = collect_versions()
    unique = set(versions.values())
    failures: list[str] = []
    for location, version in versions.items():
        print(f"  {version:<10} {location}")

    if len(unique) != 1:
        failures.append("version numbers disagree: " + ", ".join(sorted(unique)))
    version = next(iter(unique)) if len(unique) == 1 else "unknown"

    changelog = _changelog_versions(ROOT / "CHANGELOG.md")
    if version not in changelog:
        failures.append(f"CHANGELOG.md has no '## [{version}]' entry")
    else:
        print(f"  {version:<10} CHANGELOG.md")

    if args.tag:
        expected = f"v{version}"
        if args.tag != expected:
            failures.append(f"release tag {args.tag!r} does not match package version {version!r}")
        else:
            print(f"  {version:<10} release tag {args.tag}")

    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return 1
    print("versions are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
