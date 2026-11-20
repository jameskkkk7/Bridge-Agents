"""Release metadata must stay consistent before artifacts are published."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_version.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_versions_are_consistent() -> None:
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0.1.0" in result.stdout
    assert "versions are consistent" in result.stdout


def test_release_tag_must_match_the_package_version() -> None:
    result = _run("--tag", "v9.9.9")
    assert result.returncode == 1
    assert "does not match" in result.stdout + result.stderr


def test_matching_release_tag_is_accepted() -> None:
    result = _run("--tag", "v0.1.0")
    assert result.returncode == 0, result.stdout + result.stderr
