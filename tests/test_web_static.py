"""Serve the built web UI from the API process when it is present."""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def _web_app(dist: Path):
    return create_app(Settings(web_dist_dir=str(dist)))


async def test_built_web_ui_is_served_on_the_api_port(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Bridge UI</title>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('bridge');", encoding="utf-8")

    app = _web_app(dist)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        root = await client.get("/")
        assert root.status_code == 200
        assert "Bridge UI" in root.text

        spa_route = await client.get("/admin/studio")
        assert spa_route.status_code == 200
        assert "Bridge UI" in spa_route.text

        asset = await client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "console.log" in asset.text

        missing_api = await client.get("/api/v1/not-a-route")
        assert missing_api.status_code == 404
        assert missing_api.headers["content-type"].startswith("application/json")

        health = await client.get("/health")
        assert health.json()["status"] == "ok"


async def test_api_root_stays_json_without_a_web_build(tmp_path: Path) -> None:
    app = create_app(Settings(web_dist_dir=str(tmp_path / "missing")))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        root = await client.get("/")
        assert root.status_code == 200
        assert root.json()["name"] == "Bridge-Agents"
        assert (await client.get("/admin/studio")).status_code == 404
