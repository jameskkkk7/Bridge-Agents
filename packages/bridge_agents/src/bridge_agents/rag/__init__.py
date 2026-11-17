"""Hybrid retrieval-augmented generation support.

* :mod:`bridge_agents.rag.documents` — heading-aware chunking;
* :mod:`bridge_agents.rag.embeddings` — deterministic local and OpenAI back ends;
* :mod:`bridge_agents.rag.index` — hybrid vector + lexical index;
* :mod:`bridge_agents.rag.knowledge` — directory-backed runtime knowledge base;
* :mod:`bridge_agents.rag.format` — prompt and citation formatting.
"""

from __future__ import annotations

from bridge_agents.rag.documents import Chunk, load_documents, split_markdown, tokenize
from bridge_agents.rag.embeddings import Embedder, HashedEmbedder, OpenAIEmbedder
from bridge_agents.rag.format import (
    format_context,
    format_context_blocks,
    format_tool_result,
    sources_payload,
)
from bridge_agents.rag.index import DEFAULT_MIN_SCORE, DEFAULT_TOP_K, KnowledgeIndex, SearchHit
from bridge_agents.rag.knowledge import (
    DEFAULT_KNOWLEDGE_DIR,
    KnowledgeBase,
    build_embedder,
    build_knowledge,
    get_knowledge,
    refresh_knowledge,
    reset_knowledge,
)

__all__ = [
    "DEFAULT_KNOWLEDGE_DIR",
    "DEFAULT_MIN_SCORE",
    "DEFAULT_TOP_K",
    "Chunk",
    "Embedder",
    "HashedEmbedder",
    "KnowledgeBase",
    "KnowledgeIndex",
    "OpenAIEmbedder",
    "SearchHit",
    "build_embedder",
    "build_knowledge",
    "format_context",
    "format_context_blocks",
    "format_tool_result",
    "get_knowledge",
    "load_documents",
    "refresh_knowledge",
    "reset_knowledge",
    "sources_payload",
    "split_markdown",
    "tokenize",
]
