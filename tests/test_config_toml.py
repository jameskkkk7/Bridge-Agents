"""Optional TOML configuration file and its precedence rules."""

from __future__ import annotations

from pathlib import Path

from bridge_agents.config import Settings


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "bridge-agents.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_toml_values_are_loaded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from the repository .env file
    config = _write_config(tmp_path, "port = 8123\nopenai_temperature = 0.25\n")
    monkeypatch.setenv("BRIDGE_CONFIG", str(config))
    monkeypatch.delenv("PORT", raising=False)
    settings = Settings()
    assert settings.port == 8123
    assert settings.openai_temperature == 0.25


def test_environment_variables_override_the_toml_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config = _write_config(tmp_path, "port = 8123\n")
    monkeypatch.setenv("BRIDGE_CONFIG", str(config))
    monkeypatch.setenv("PORT", "9000")
    assert Settings().port == 9000


def test_missing_toml_file_falls_back_to_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRIDGE_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.delenv("PORT", raising=False)
    assert Settings().port == 8000
