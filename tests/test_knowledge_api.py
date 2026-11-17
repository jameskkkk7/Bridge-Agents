"""Admin knowledge base API: status, search, uploads and reindexing."""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers import bearer, dev_login


async def _agent_headers(client: AsyncClient) -> dict[str, str]:
    login = await dev_login(client, "agent")
    return bearer(login["access_token"])


async def test_knowledge_endpoints_require_staff(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/knowledge/status")).status_code == 401
    customer = await dev_login(client, "user")
    response = await client.get(
        "/api/v1/admin/knowledge/status", headers=bearer(customer["access_token"])
    )
    assert response.status_code == 403


async def test_status_lists_the_seeded_documents(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.get("/api/v1/admin/knowledge/status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] >= 2
    assert body["chunk_count"] > body["document_count"]
    assert body["embedder"] == "hash"
    assert body["dimension"] == 256
    names = {document["name"] for document in body["documents"]}
    assert {"widget-pro.md", "widget-cloud.md"} <= names
    assert all(document["chunks"] >= 1 for document in body["documents"])


async def test_search_returns_citable_passages(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.get(
        "/api/v1/admin/knowledge/search",
        params={"query": "How do I activate Widget Pro?", "top_k": 3},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"].startswith("How do I activate")
    assert body["elapsed_ms"] >= 0
    assert body["hits"]
    first = body["hits"][0]
    assert first["index"] == 1
    assert first["citation"]
    assert first["preview"]
    assert {"score", "vector_score", "lexical_score"} <= set(first)


async def test_search_requires_a_query(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.get("/api/v1/admin/knowledge/search", headers=headers)
    assert response.status_code == 422


async def test_upload_reindex_delete_round_trip(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    document = b"# Shipping FAQ\n\n## Delivery\n\nOrders ship within five business days."

    uploaded = await client.post(
        "/api/v1/admin/knowledge/documents",
        files={"file": ("shipping.md", document, "text/markdown")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["saved"] is True
    assert body["document"]["name"] == "shipping.md"
    assert body["document"]["chunks"] >= 1

    search = await client.get(
        "/api/v1/admin/knowledge/search",
        params={"query": "how long does delivery take", "top_k": 3},
        headers=headers,
    )
    citations = [hit["citation"] for hit in search.json()["hits"]]
    assert any("Shipping FAQ" in citation for citation in citations)

    reindexed = await client.post("/api/v1/admin/knowledge/reindex", headers=headers)
    assert reindexed.status_code == 200
    assert reindexed.json()["chunk_count"] >= 1

    deleted = await client.delete("/api/v1/admin/knowledge/documents/shipping.md", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    missing = await client.delete("/api/v1/admin/knowledge/documents/shipping.md", headers=headers)
    assert missing.status_code == 404


async def test_upload_rejects_unsupported_documents(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.post(
        "/api/v1/admin/knowledge/documents",
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "markdown" in response.json()["message"].lower()


async def test_upload_rejects_empty_text(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.post(
        "/api/v1/admin/knowledge/documents",
        files={"file": ("empty.md", b"   ", "text/markdown")},
        headers=headers,
    )
    assert response.status_code == 422


async def test_document_listing(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    response = await client.get("/api/v1/admin/knowledge/documents", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.json()
