"""Saved API profiles: validation state, activation and deletion."""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers import bearer, dev_login


async def _agent_headers(client: AsyncClient) -> dict[str, str]:
    login = await dev_login(client, "agent")
    return bearer(login["access_token"])


def _profile_payload(**overrides) -> dict:
    payload = {
        "name": "Production OpenAI",
        "provider": "openai",
        "base_url": "https://llm.example.test/v1",
        "model": "profile-model",
        "api_key": "sk-profile-secret",
        "temperature": 0.4,
        "timeout": 30,
        "max_retries": 2,
    }
    payload.update(overrides)
    return payload


def _fake_validation(valid: bool = True, message: str = "ok"):
    async def fake(**_kwargs) -> tuple[bool, str]:
        return valid, message

    return fake


async def test_model_profiles_require_staff(client: AsyncClient) -> None:
    assert (
        await client.get("/api/v1/admin/runtime-config/model-config/profiles")
    ).status_code == 401
    customer = await dev_login(client, "user")
    response = await client.get(
        "/api/v1/admin/runtime-config/model-config/profiles",
        headers=bearer(customer["access_token"]),
    )
    assert response.status_code == 403


async def test_create_and_list_a_validated_profile(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.model_profiles_service.validate_model_config", _fake_validation()
    )
    headers = await _agent_headers(client)
    created = await client.post(
        "/api/v1/admin/runtime-config/model-config/profiles",
        json=_profile_payload(),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Production OpenAI"
    assert body["valid"] is True
    assert body["active"] is False
    assert body["api_key_configured"] is True
    assert "sk-profile-secret" not in created.text

    listed = await client.get("/api/v1/admin/runtime-config/model-config/profiles", headers=headers)
    assert listed.status_code == 200
    listing = listed.json()
    assert listing["active_id"] is None
    assert len(listing["profiles"]) == 1
    assert listing["profiles"][0]["id"] == body["id"]
    assert "sk-profile-secret" not in listed.text


async def test_activate_and_deactivate_a_profile(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.model_profiles_service.validate_model_config", _fake_validation()
    )
    headers = await _agent_headers(client)
    created = (
        await client.post(
            "/api/v1/admin/runtime-config/model-config/profiles",
            json=_profile_payload(),
            headers=headers,
        )
    ).json()

    activated = await client.post(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}/activate",
        headers=headers,
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["active"] is True

    effective = await client.get("/api/v1/admin/runtime-config/model-config", headers=headers)
    assert effective.json()["source"] == "runtime"
    assert effective.json()["model"] == "profile-model"
    assert effective.json()["base_url"] == "https://llm.example.test/v1"

    listing = (
        await client.get("/api/v1/admin/runtime-config/model-config/profiles", headers=headers)
    ).json()
    assert listing["active_id"] == created["id"]

    deactivated = await client.post(
        "/api/v1/admin/runtime-config/model-config/profiles/deactivate", headers=headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active_id"] is None
    effective = await client.get("/api/v1/admin/runtime-config/model-config", headers=headers)
    assert effective.json()["source"] == "environment"


async def test_invalid_profile_cannot_be_activated(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.model_profiles_service.validate_model_config",
        _fake_validation(False, "provider returned HTTP 401"),
    )
    headers = await _agent_headers(client)
    created = (
        await client.post(
            "/api/v1/admin/runtime-config/model-config/profiles",
            json=_profile_payload(),
            headers=headers,
        )
    ).json()
    assert created["valid"] is False
    assert "401" in created["validation_message"]

    response = await client.post(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}/activate",
        headers=headers,
    )
    assert response.status_code == 422


async def test_validate_update_and_delete_profiles(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.model_profiles_service.validate_model_config", _fake_validation()
    )
    headers = await _agent_headers(client)
    created = (
        await client.post(
            "/api/v1/admin/runtime-config/model-config/profiles",
            json=_profile_payload(),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}/activate",
        headers=headers,
    )

    updated = await client.put(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}",
        json=_profile_payload(name="Renamed", model="profile-model-v2", api_key=None),
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["api_key_configured"] is True

    monkeypatch.setattr(
        "app.services.model_profiles_service.validate_model_config",
        _fake_validation(False, "model not available"),
    )
    validated = await client.post(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}/validate",
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.json()["valid"] is False

    deleted = await client.delete(
        f"/api/v1/admin/runtime-config/model-config/profiles/{created['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["active_id"] is None
    assert deleted.json()["profiles"] == []
    effective = await client.get("/api/v1/admin/runtime-config/model-config", headers=headers)
    assert effective.json()["source"] == "environment"
