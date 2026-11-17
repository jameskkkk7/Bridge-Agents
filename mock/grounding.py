"""Deterministic helpers for the mock model: embeddings and grounded replies.

Keeping them out of ``main.py`` keeps the request handling readable and the
mock within the repository's per-file size budget.
"""

from __future__ import annotations

import hashlib
import math
import re

KNOWLEDGE_MARKER = "Retrieved knowledge for this question"
EMBEDDING_DIMENSION = 256
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def embedding_vector(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Deterministic hashed bag-of-words vector (no model weights involved)."""
    vector = [0.0] * dimension
    terms = re.findall(r"[a-z0-9]+", text.lower())
    if not terms:
        return vector
    counts: dict[str, int] = {}
    for term in terms:
        counts[term] = counts.get(term, 0) + 1
    for term, count in counts.items():
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        vector[value % dimension] += (1.0 if (value >> 63) & 1 else -1.0) * (1.0 + math.log(count))
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [round(item / norm, 6) for item in vector]


def knowledge_context(messages: list[dict], content_text) -> str:
    """Return the retrieved-knowledge system block, if the runtime injected one."""
    for message in messages:
        if message.get("role") != "system":
            continue
        text = content_text(message.get("content"))
        if KNOWLEDGE_MARKER in text:
            return text
    return ""


def knowledge_segments(messages: list[dict], content_text) -> list[str]:
    """Answer from the first retrieved passage and cite it."""
    context = knowledge_context(messages, content_text)
    if not context:
        return []
    blocks = re.split(r"\n\[(\d+)\]\s+", context)
    if len(blocks) < 3:
        return []
    citation, _, body = blocks[2].partition("\n")
    body = " ".join(body.split())
    if not body:
        return []
    sentences = [part.strip() for part in _SENTENCE_END.split(body) if part.strip()]
    excerpt = sentences[0] if sentences else body
    if len(excerpt) > 220:
        excerpt = excerpt[:220].rstrip() + "..."
    return [
        f"According to the documentation ({citation}): ",
        f"{excerpt} ",
        f"[{blocks[1]}]",
    ]
