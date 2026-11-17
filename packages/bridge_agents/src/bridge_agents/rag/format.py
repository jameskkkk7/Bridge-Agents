"""Prompt formatting for retrieved passages."""

from __future__ import annotations

from bridge_agents.rag.index import SearchHit

CONTEXT_HEADER = (
    "Retrieved knowledge for this question. Use it when it is relevant, and cite "
    "the sources in square brackets like [1]. If the knowledge does not answer "
    "the question, say what you do not know instead of guessing."
)


def format_context_blocks(
    entries: list[dict], *, max_chars: int = 2400, header: str = CONTEXT_HEADER
) -> str:
    """Render plain retrieved-source dictionaries into a numbered context block.

    The pipeline stores retrieval results as dictionaries in graph state, so the
    same formatter works for live :class:`SearchHit` objects and stored state.
    The budget is a hard limit: one oversized passage is truncated rather than
    letting a single chunk swallow the whole prompt.
    """
    if not entries:
        return ""
    budget = max(0, max_chars - len(header) - 2)
    lines = [header]
    used = 0
    for position, entry in enumerate(entries, start=1):
        citation = entry.get("citation") or entry.get("document") or "source"
        body = " ".join(str(entry.get("text", "")).split())
        if not body:
            continue
        prefix = f"[{position}] {citation}\n"
        remaining = budget - used - len(prefix) - 2
        if remaining < 40:
            break
        if len(body) > remaining:
            body = body[:remaining].rstrip() + "…"
        block = prefix + body
        lines.append(block)
        used += len(block) + 2
    return "\n\n".join(lines)


def format_context(hits: list[SearchHit], *, max_chars: int = 2400) -> str:
    """Render hits into a numbered context block for the model prompt."""
    return format_context_blocks([hit.chunk.as_dict() for hit in hits], max_chars=max_chars)


def format_tool_result(hits: list[SearchHit], *, max_chars: int = 1200) -> str:
    """Render hits for a tool result: concise excerpts with citations."""
    if not hits:
        return ""
    blocks: list[str] = []
    for position, hit in enumerate(hits, start=1):
        excerpt = " ".join(hit.chunk.text.split())
        if len(excerpt) > max_chars // max(1, len(hits)):
            excerpt = excerpt[: max_chars // max(1, len(hits))].rstrip() + "..."
        blocks.append(f"[{position}] {hit.chunk.citation()}\n{excerpt}")
    return "\n\n".join(blocks)


def sources_payload(hits: list[SearchHit]) -> list[dict]:
    """Structured sources for API responses and the browser demo."""
    return [
        {
            "index": position,
            "citation": hit.chunk.citation(),
            "document": hit.chunk.document,
            "heading": hit.chunk.heading,
            "source": hit.chunk.source,
            "chunk_id": hit.chunk.id,
            "score": round(hit.score, 4),
            "vector_score": round(hit.vector_score, 4),
            "lexical_score": round(hit.lexical_score, 4),
            "preview": " ".join(hit.chunk.text.split())[:240],
        }
        for position, hit in enumerate(hits, start=1)
    ]
