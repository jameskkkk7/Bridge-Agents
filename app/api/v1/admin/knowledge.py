"""Admin knowledge base endpoints: status, search, uploads and reindexing.

The runtime uses the same knowledge base automatically through the graph's
``retrieval`` node and the ``search_docs`` tool; these routes expose it to the
studio UI for inspection and maintenance.
"""

from __future__ import annotations

import time
from pathlib import Path

from bridge_agents.rag.format import sources_payload
from bridge_agents.rag.knowledge import MAX_DOCUMENT_BYTES
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from app.api.deps import require_agent
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeDeleted,
    KnowledgeDocument,
    KnowledgeDocumentSaved,
    KnowledgeHit,
    KnowledgeSearchResult,
    KnowledgeStatus,
)
from app.services.knowledge_service import knowledge_for, rebuild_knowledge

router = APIRouter()


def _document_entry(name: str, entries: list[dict]) -> KnowledgeDocument:
    for entry in entries:
        if entry["name"] == name:
            return KnowledgeDocument(**entry)
    return KnowledgeDocument(name=name, bytes=0, modified=0.0, chunks=0)


def _status_payload(base) -> KnowledgeStatus:
    stats = base.stats()
    return KnowledgeStatus(
        document_count=stats["documents"],
        chunk_count=stats["chunks"],
        term_count=stats["terms"],
        dimension=stats["dimension"],
        embedder=stats["embedder"],
        built_at=stats["built_at"],
        directory=stats["directory"],
        top_k=stats["top_k"],
        min_score=stats["min_score"],
        chunk_size=stats["chunk_size"],
        chunk_overlap=stats["chunk_overlap"],
        documents=[KnowledgeDocument(**entry) for entry in base.documents()],
    )


@router.get("/status", response_model=KnowledgeStatus)
async def knowledge_status(request: Request, _: User = Depends(require_agent)) -> KnowledgeStatus:
    """Return index statistics and the document list."""
    return _status_payload(knowledge_for(request.app))


@router.get("/search", response_model=KnowledgeSearchResult)
async def knowledge_search(
    request: Request,
    query: str = Query(min_length=1, max_length=500),
    top_k: int = Query(default=4, ge=1, le=20),
    _: User = Depends(require_agent),
) -> KnowledgeSearchResult:
    """Preview what the retriever returns for a question."""
    base = knowledge_for(request.app)
    started = time.perf_counter()
    hits = base.search(query, top_k=top_k)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return KnowledgeSearchResult(
        query=query,
        hits=[KnowledgeHit(**entry) for entry in sources_payload(hits)],
        elapsed_ms=elapsed_ms,
    )


@router.post("/reindex", response_model=KnowledgeStatus)
async def reindex_knowledge(request: Request, _: User = Depends(require_agent)) -> KnowledgeStatus:
    """Rebuild the index from the knowledge directory."""
    return _status_payload(rebuild_knowledge(request.app))


@router.get("/documents", response_model=list[KnowledgeDocument])
async def list_knowledge_documents(
    request: Request, _: User = Depends(require_agent)
) -> list[KnowledgeDocument]:
    """List the documents that make up the knowledge base."""
    return [KnowledgeDocument(**entry) for entry in knowledge_for(request.app).documents()]


@router.post("/documents", response_model=KnowledgeDocumentSaved, status_code=201)
async def upload_knowledge_document(
    request: Request,
    file: UploadFile = File(description="Markdown or text document"),
    _: User = Depends(require_agent),
) -> KnowledgeDocumentSaved:
    """Upload or replace one document and reindex."""
    base = knowledge_for(request.app)
    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    name = Path(file.filename or "document.md").name
    try:
        target = base.save_document(name, content)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return KnowledgeDocumentSaved(
        saved=True, document=_document_entry(target.name, base.documents())
    )


@router.delete("/documents/{name}", response_model=KnowledgeDeleted)
async def delete_knowledge_document(
    request: Request, name: str, _: User = Depends(require_agent)
) -> KnowledgeDeleted:
    """Delete one document and reindex."""
    base = knowledge_for(request.app)
    try:
        deleted = base.delete_document(name)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValidationError(str(exc)) from exc
    if not deleted:
        raise NotFoundError("Document not found")
    return KnowledgeDeleted(deleted=True)
