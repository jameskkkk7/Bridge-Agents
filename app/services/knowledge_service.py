"""Knowledge base access for the application layer."""

from __future__ import annotations

import logging

from bridge_agents.rag.knowledge import KnowledgeBase, get_knowledge, refresh_knowledge
from fastapi import FastAPI

LOGGER = logging.getLogger(__name__)


def knowledge_for(application: FastAPI) -> KnowledgeBase:
    """Return the knowledge base bound to this application (lazy singleton)."""
    base = getattr(application.state, "knowledge", None)
    if base is None:
        base = get_knowledge()
        application.state.knowledge = base
    return base


def initialize_knowledge(application: FastAPI) -> KnowledgeBase:
    """Build the index during startup, tolerating an unreachable embedder.

    With the default hashed embedder this is a local operation. With an HTTP
    embedding provider an outage must not stop the API from starting: the
    knowledge base stays empty and the admin API reports the failure.
    """
    base = get_knowledge()
    try:
        base.reload()
    except Exception:
        LOGGER.exception("knowledge base indexing failed at startup; continuing without it")
    application.state.knowledge = base
    return base


def rebuild_knowledge(application: FastAPI) -> KnowledgeBase:
    """Force a full reindex and rebind it to the application."""
    base = refresh_knowledge()
    base.reload(force=True)
    application.state.knowledge = base
    return base
