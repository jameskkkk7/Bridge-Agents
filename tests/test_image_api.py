"""Image upload, download and ownership rules."""

from __future__ import annotations

from httpx import AsyncClient

from app.services.image_service import image_id_from_content
from tests.helpers import bearer, create_user, dev_login, make_token

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


async def _login(client: AsyncClient, role: str = "user") -> str:
    body = await dev_login(client, role)
    return body["access_token"]


async def _create_session(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/sessions", json={"title": "Images"}, headers=bearer(token)
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_upload_creates_an_image_message_and_serves_the_file(
    client: AsyncClient,
) -> None:
    token = await _login(client)
    session_id = await _create_session(client, token)

    uploaded = await client.post(
        f"/api/v1/sessions/{session_id}/images",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=bearer(token),
    )
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    assert image["mime_type"] == "image/png"
    assert image["file_size"] == len(PNG_BYTES)

    downloaded = await client.get(
        f"/api/v1/sessions/{session_id}/images/{image['id']}", headers=bearer(token)
    )
    assert downloaded.status_code == 200
    assert downloaded.content == PNG_BYTES

    history = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=bearer(token))
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["message_type"] == "image"
    assert image_id_from_content(items[0]["content"]) == image["id"]


async def test_unsupported_image_type_is_rejected(client: AsyncClient) -> None:
    token = await _login(client)
    session_id = await _create_session(client, token)
    response = await client.post(
        f"/api/v1/sessions/{session_id}/images",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=bearer(token),
    )
    assert response.status_code == 422
    assert response.json()["error"] == "ValidationError"


async def test_image_endpoints_require_ownership(client: AsyncClient, db_session) -> None:
    owner_token = await _login(client)
    session_id = await _create_session(client, owner_token)
    uploaded = await client.post(
        f"/api/v1/sessions/{session_id}/images",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=bearer(owner_token),
    )
    image_id = uploaded.json()["id"]

    intruder = await create_user(db_session, "intruder-images@example.test")
    intruder_token = make_token(intruder.id, "USER")
    assert (
        await client.get(
            f"/api/v1/sessions/{session_id}/images/{image_id}",
            headers=bearer(intruder_token),
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/sessions/{session_id}/images",
            files={"file": ("photo.png", PNG_BYTES, "image/png")},
            headers=bearer(intruder_token),
        )
    ).status_code == 403


async def test_image_must_belong_to_the_session_in_the_path(client: AsyncClient) -> None:
    token = await _login(client)
    first = await _create_session(client, token)
    second = await _create_session(client, token)
    uploaded = await client.post(
        f"/api/v1/sessions/{first}/images",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        headers=bearer(token),
    )
    image_id = uploaded.json()["id"]

    response = await client.get(
        f"/api/v1/sessions/{second}/images/{image_id}", headers=bearer(token)
    )
    assert response.status_code == 404
