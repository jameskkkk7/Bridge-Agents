"""Schemas for the admin knowledge base API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    """One file in the knowledge directory."""

    name: str
    bytes: int
    modified: float
    chunks: int


class KnowledgeStatus(BaseModel):
    """Index and directory status shown in the demo studio."""

    document_count: int
    chunk_count: int
    term_count: int
    dimension: int
    embedder: str
    built_at: str
    directory: str
    top_k: int
    min_score: float
    chunk_size: int
    chunk_overlap: int
    documents: list[KnowledgeDocument] = Field(default_factory=list)


class KnowledgeHit(BaseModel):
    """One ranked retrieval result."""

    index: int
    citation: str
    document: str
    heading: str = ""
    source: str
    chunk_id: str
    score: float
    vector_score: float
    lexical_score: float
    preview: str


class KnowledgeSearchResult(BaseModel):
    """Answer to a retrieval preview request."""

    query: str
    hits: list[KnowledgeHit] = Field(default_factory=list)
    elapsed_ms: float


class KnowledgeDocumentSaved(BaseModel):
    """Result of uploading a document."""

    saved: bool
    document: KnowledgeDocument


class KnowledgeDeleted(BaseModel):
    """Result of deleting a document."""

    deleted: bool
