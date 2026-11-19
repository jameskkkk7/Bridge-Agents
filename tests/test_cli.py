"""CLI ergonomics: demo environment, env bootstrap and maintenance commands."""

from __future__ import annotations

from pathlib import Path

from app import cli


def test_demo_environment_uses_the_checkout_and_mock(tmp_path: Path) -> None:
    environment = cli._demo_environment(tmp_path, 8123)
    assert environment["ALLOW_DEV_LOGIN"] == "true"
    assert environment["ALLOWED_HOSTS"] == "*"
    assert environment["LLM_MODE"] == "mock"
    assert environment["OPENAI_BASE_URL"] == "http://127.0.0.1:8123/v1"
    assert environment["WEB_DIST_DIR"] == str(tmp_path / "web" / "dist")


def test_ensure_env_file_copies_the_example_once(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("LLM_MODE=mock\n", encoding="utf-8")
    created = cli._ensure_env_file(tmp_path)
    assert created == tmp_path / ".env"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "LLM_MODE=mock\n"

    (tmp_path / ".env").write_text("CUSTOM=keep-me\n", encoding="utf-8")
    assert cli._ensure_env_file(tmp_path) == tmp_path / ".env"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "CUSTOM=keep-me\n"


def test_version_command_prints_package_versions(capsys) -> None:
    assert cli.main(["version"]) == 0
    output = capsys.readouterr().out
    assert "Python" in output
    assert "bridge-agents" in output


def test_doctor_reports_the_checkout(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "Bridge-Agents doctor" in output
    assert str(tmp_path) in output
    assert "Port 8000" in output


def test_parser_accepts_the_documented_commands() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["demo", "--port", "9000"]).port == 9000
    assert parser.parse_args(["serve", "--reload"]).reload is True
    assert parser.parse_args(["init-db"]).command == "init-db"


def test_init_writes_config_and_secrets_once(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init"]) == 0
    config = (tmp_path / "bridge-agents.toml").read_text(encoding="utf-8")
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'app_env = "development"' in config
    assert "allow_dev_login = true" in config
    secret = env_text.split("JWT_SECRET=", 1)[1].splitlines()[0]
    assert len(secret) >= 32

    assert cli.main(["init"]) == 1
    assert "Refusing to overwrite" in capsys.readouterr().out


def test_init_production_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init", "--production"]) == 0
    config = (tmp_path / "bridge-agents.toml").read_text(encoding="utf-8")
    assert 'app_env = "production"' in config
    assert "allow_dev_login = false" in config


def test_config_check_reports_warnings_without_failing(tmp_path: Path, monkeypatch, capsys) -> None:
    from os import environ

    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    try:
        assert cli.main(["config", "check", "--config", "bridge-agents.toml"]) == 0
    finally:
        environ.pop("BRIDGE_CONFIG", None)
    output = capsys.readouterr().out
    assert "Effective configuration" in output
    assert "no built web UI" in output
