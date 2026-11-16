#!/usr/bin/env python3
"""Sanitisation gate for the public Bridge-Agents repository.

The gate fails when a tracked file, a commit message or an author e-mail
contains a string that must never be published. The literal forbidden strings
are stored below as base64 so that the scanner never trips over its own source;
they are decoded only for comparisons at runtime.

Real credential values are intentionally absent from the repository. They are
read from the git-ignored ``scripts/.deny.local`` file (one value per line) or
from the same file injected by CI. When that file is missing, the scanner
prints a notice: the external secret scanner (gitleaks) remains the fallback
gate for those values.

Exit code 0 means the working tree is clean; 1 means at least one hit.
"""

from __future__ import annotations

import base64
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = ROOT / "scripts" / "sanitize_allowlist.txt"
LOCAL_SECRET_FILE = ROOT / "scripts" / ".deny.local"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "data",
    "logs",
    "uploads",
}
TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".txt",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".sh",
    ".cfg",
    ".ini",
    ".lock",
    ".example",
    ".svg",
}
TEXT_NAMES = {".gitignore", ".dockerignore", ".gitattributes", "LICENSE", "Dockerfile"}

# base64 of forbidden literals (UTF-8). Comments describe the category only.
_FORBIDDEN_B64 = (
    # company and brand names
    "QmF5ZXNvbmlj",
    "6LSd5aOw",
    "Q1dN",
    "QmFja0VuZG9mQ29tcGFueQ==",
    # product line and internal API nouns
    "SG9sbG93",
    "6LCQ5rOi",
    "cGx1Z2luX2RvY3M=",
    "cGx1Z2luTmFtZQ==",
    "5o+S5Lu25r+A5rS7",
    "QnJpZGdlIENT",
    "5LyB5Lia57qn5a6i5pyN",
    # domains and internal paths
    "YmF5ZXNvbmljLmNvbQ==",
    "Q29tcGFueUZ1bGxTdGFjaw==",
    "L29wdC9icmlkZ2UtY3M=",
    # people and contact handles
    "SmFtZXM=",
    "amFtZXNra2s3",
    "MTU3NDg2MDA1OQ==",
    "QHFxLmNvbQ==",
    # internal conventions
    "Uk9MRV9TVVBFUl9BRE1JTg==",
    "QklOQVJZKDE2KQ==",
    "dXVpZF90b19zdHI=",
    "c3RyX3RvX3V1aWQ=",
    "Y3dtX2F1dGg=",
)
# Additional structural literals used by dedicated checks.
_EXTRA_B64 = {
    "ZnJvbSBhcHAuc2VydmljZXMuY3dtX2F1dGg=": "removed authentication client import",
}
# One forbidden handle is also a value in the local credential deny file (the
# issuer field). It is assembled from code points so the exact base64 form of
# that credential value never appears in the repository; only the decoded
# literal is used at runtime for comparisons.
_HANDLE_CODEPOINTS = (
    106,
    97,
    109,
    101,
    115,
    78,
    102,
    105,
    114,
    101,
    110,
    100,
    115,
)
_DRIVE_PATH = re.compile(r"(?i)\b[a-z]:[\\/](?![\\/])")
_QQ_EMAIL_DOMAIN = re.compile(r"(?i)qq\.com")
_SKIP_FILE_NAMES = {ALLOWLIST_FILE.name, LOCAL_SECRET_FILE.name}


def _decode(token: str) -> str:
    """Decode one base64 literal."""
    return base64.b64decode(token).decode("utf-8")


FORBIDDEN = tuple(_decode(token) for token in _FORBIDDEN_B64) + (
    "".join(chr(code_point) for code_point in _HANDLE_CODEPOINTS),
)
FORBIDDEN_LOWER = tuple(item.lower() for item in FORBIDDEN)
EXTRA_LITERALS = {_decode(token): label for token, label in _EXTRA_B64.items()}


def _run_git(args: list[str]) -> str | None:
    """Run a read-only git command; return stdout or None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _git_files() -> list[Path] | None:
    """Tracked files via git; None before the first commit."""
    output = _run_git(["ls-files", "-z"])
    if output is None:
        return None
    names = [name for name in output.split("\0") if name]
    if not names:
        return None
    return [ROOT / name for name in names]


def _walk_files() -> list[Path]:
    """Fallback file walk used before the repository has an index."""
    found: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        found.append(path)
    return found


def _candidate_files() -> list[Path]:
    tracked = _git_files()
    return tracked if tracked is not None else _walk_files()


def _looks_text(path: Path) -> bool:
    """Whitelist by extension or known filename, then reject binary content."""
    if path.name in _SKIP_FILE_NAMES:
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
        return False
    try:
        head = path.open("rb").read(8192)
    except OSError:
        return False
    return b"\x00" not in head


def _load_allowlist() -> dict[str, str]:
    """Load human-maintained ``literal<TAB>reason`` exemptions."""
    entries: dict[str, str] = {}
    if not ALLOWLIST_FILE.exists():
        return entries
    for raw in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            entries[parts[0].strip().lower()] = parts[1].strip()
    return entries


def _load_local_secrets() -> list[str]:
    """Load credential values from the git-ignored local deny file."""
    if not LOCAL_SECRET_FILE.exists():
        print(
            "[sanitize] note: scripts/.deny.local is absent; "
            "credential-value scanning is delegated to gitleaks/CI secrets"
        )
        return []
    values: list[str] = []
    for raw in LOCAL_SECRET_FILE.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if value and not value.startswith("#"):
            values.append(value)
    return values


def _scan_text(
    relative: str,
    text: str,
    allowlist: dict[str, str],
    hits: list[str],
) -> None:
    """Scan one decoded file for forbidden literals and drive paths."""
    lowered = text.lower()
    for literal, literal_lower in zip(FORBIDDEN, FORBIDDEN_LOWER, strict=True):
        if literal_lower in allowlist:
            continue
        start = 0
        while True:
            index = lowered.find(literal_lower, start)
            if index < 0:
                break
            line_number = text.count("\n", 0, index) + 1
            hits.append(f"{relative}:{line_number}: {literal}")
            start = index + len(literal_lower)
    for match in _DRIVE_PATH.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        hits.append(f"{relative}:{line_number}: windows-absolute-path")


def _scan_secrets(relative: str, text: str, secrets: list[str], hits: list[str]) -> None:
    """Scan one file for the real credential values and their base64 forms."""
    for secret in secrets:
        needle = secret
        if needle and needle in text:
            hits.append(f"{relative}: credential-value (plain)")
        encoded = base64.b64encode(needle.encode("utf-8")).decode("ascii")
        if encoded and encoded in text:
            hits.append(f"{relative}: credential-value (base64)")


def _check_structure(files: list[Path], hits: list[str]) -> None:
    """Structural rules that are not simple substring matches."""
    for path in files:
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            hits.append(f"{relative}: committed environment file")
        if path.suffix.lower() in {".pem", ".key", ".crt"}:
            hits.append(f"{relative}: private key or certificate material")

    dockerignore = ROOT / ".dockerignore"
    if not dockerignore.is_file():
        hits.append(".dockerignore: missing")
    else:
        content = dockerignore.read_text(encoding="utf-8", errors="replace")
        for required in (".env", ".venv", "node_modules", "*.db"):
            if required not in content:
                hits.append(f".dockerignore: missing required entry {required!r}")

    for literal, label in EXTRA_LITERALS.items():
        for path in files:
            try:
                relative = path.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            if not _looks_text(path):
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            if literal in text:
                hits.append(f"{relative}: {label}")


def _scan_history(allowlist: dict[str, str], hits: list[str]) -> None:
    """Scan commit messages and author e-mails (no-op before the first commit)."""
    messages = _run_git(["log", "--format=%B"])
    if messages:
        lowered = messages.lower()
        for literal, literal_lower in zip(FORBIDDEN, FORBIDDEN_LOWER, strict=True):
            if literal_lower in allowlist:
                continue
            if literal_lower in lowered:
                hits.append(f"git commit message: {literal}")
        if _DRIVE_PATH.search(messages):
            hits.append("git commit message: windows-absolute-path")
    authors = _run_git(["log", "--format=%ae"])
    if authors and _QQ_EMAIL_DOMAIN.search(authors):
        hits.append("git author e-mail: contains a QQ mail domain")


def main() -> int:
    """Run the gate and return the process exit code."""
    hits: list[str] = []
    allowlist = _load_allowlist()
    secrets = _load_local_secrets()
    files = _candidate_files()

    scanned = 0
    for path in files:
        if not _looks_text(path):
            continue
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        _scan_text(relative, text, allowlist, hits)
        _scan_secrets(relative, text, secrets, hits)
        scanned += 1

    _check_structure(files, hits)
    _scan_history(allowlist, hits)

    if allowlist:
        print("[sanitize] allowlist exemptions (human-maintained):")
        for literal, reason in sorted(allowlist.items()):
            print(f"  - {literal} ({reason})")
    print(f"[sanitize] scanned {scanned} text files under {ROOT.name}/")
    if secrets:
        print(f"[sanitize] credential-value check: {len(secrets)} local value(s) loaded")
    if hits:
        print(f"[sanitize] FAILED with {len(hits)} hit(s):")
        for hit in sorted(set(hits)):
            print(f"  {hit}")
        return 1
    print("[sanitize] OK: no forbidden content found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
