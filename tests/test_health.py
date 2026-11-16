"""Operational endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_reports_status(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


async def test_root_advertises_the_product(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Bridge-Agents"
    assert body["docs"] is None
