"""Tests for environment driven settings."""

from __future__ import annotations

from app.config import Settings, get_settings


def test_comma_separated_values_are_exposed_as_lists() -> None:
    settings = Settings(
        cors_origins="http://localhost:5173, http://localhost:8080",
        allowed_hosts="localhost, 127.0.0.1",
    )
    assert settings.cors_origin_list == ["http://localhost:5173", "http://localhost:8080"]
    assert settings.allowed_host_list == ["localhost", "127.0.0.1"]


def test_empty_lists_use_safe_defaults() -> None:
    settings = Settings(cors_origins="", allowed_hosts="")
    assert settings.cors_origin_list == []
    assert settings.allowed_host_list == ["*"]


def test_environment_name_is_normalized() -> None:
    settings = Settings(app_env=" Production ")
    assert settings.app_env == "production"
    assert settings.is_production is True


def test_secure_demo_defaults_are_off() -> None:
    # The class defaults are what a fresh checkout ships with; the test
    # environment overrides them for the demo endpoints.
    assert Settings.model_fields["allow_dev_login"].default is False
    assert Settings.model_fields["llm_mode"].default == "mock"
    assert Settings.model_fields["auth_verifier"].default == "hs256"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
