"""Hybrid retrieval index over document chunks."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from bridge_agents.rag.documents import Chunk, stem, tokenize
from bridge_agents.rag.embeddings import Embedder

DEFAULT_TOP_K = 4
DEFAULT_MIN_SCORE = 0.12
# Reciprocal weighting of the two signals; lexical matters because product
# names and error codes are exact tokens that embeddings blur.
VECTOR_WEIGHT = 0.6
LEXICAL_WEIGHT = 0.4


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One ranked passage with the scores that produced the ranking."""

    chunk: Chunk
    score: float
    vector_score: float
    lexical_score: float

    def as_dict(self) -> dict:
        return {
            **self.chunk.as_dict(),
            "score": round(self.score, 4),
            "vector_score": round(self.vector_score, 4),
            "lexical_score": round(self.lexical_score, 4),
        }


def _embedding_text(chunk: Chunk) -> str:
    """Text used for the vector; the title repeats the heading on purpose."""
    parts = [chunk.document]
    if chunk.heading:
        parts.append(chunk.heading)
    parts.append(chunk.text)
    return "\n".join(parts)


class KnowledgeIndex:
    """Immutable hybrid index: cosine similarity plus TF-IDF lexical match."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder) -> None:
        self.chunks = list(chunks)
        self.embedder = embedder
        self.built_at = datetime.now(UTC)
        self._term_counts: list[Counter[str]] = []
        self._heading_counts: list[Counter[str]] = []
        self._document_frequency: Counter[str] = Counter()
        self._vectors: list[list[float]] = []
        if self.chunks:
            self._vectors = embedder.embed_documents(
                [_embedding_text(chunk) for chunk in self.chunks]
            )
        for chunk in self.chunks:
            counts = Counter(
                stem(term) for term in tokenize(f"{chunk.document} {chunk.heading} {chunk.text}")
            )
            self._term_counts.append(counts)
            self._document_frequency.update(counts.keys())
            self._heading_counts.append(Counter(stem(term) for term in tokenize(chunk.heading)))

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def _idf(self, term: str) -> float:
        total = len(self.chunks)
        frequency = self._document_frequency.get(term, 0)
        return math.log((total + 1) / (frequency + 1)) + 1.0

    def _lexical_scores(self, query_terms: list[str]) -> list[float]:
        query_stems = {stem(term) for term in query_terms}
        raw: list[float] = []
        for position, counts in enumerate(self._term_counts):
            heading_counts = self._heading_counts[position]
            score = 0.0
            for query_stem in query_stems:
                for term, frequency in counts.items():
                    if term == query_stem:
                        score += self._idf(term) * (1.0 + math.log(frequency))
                    elif (
                        len(term) >= 4
                        and len(query_stem) >= 4
                        and (term.startswith(query_stem) or query_stem.startswith(term))
                    ):
                        # Near-miss stems ("policy" / "policies") still count.
                        score += 0.6 * self._idf(term) * (1.0 + math.log(frequency))
                heading_frequency = heading_counts.get(query_stem, 0)
                if heading_frequency:
                    # A matching section heading is a stronger signal than body text.
                    score += 2.0 * self._idf(query_stem) * (1.0 + math.log(heading_frequency))
            length = math.sqrt(sum(value * value for value in counts.values())) or 1.0
            raw.append(score / length)
        peak = max(raw, default=0.0)
        if peak <= 0:
            return [0.0 for _ in raw]
        return [value / peak for value in raw]

    @staticmethod
    def _dot(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return float(sum(a * b for a, b in zip(left, right, strict=False)))

    def search(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        vector_weight: float = VECTOR_WEIGHT,
        lexical_weight: float = LEXICAL_WEIGHT,
    ) -> list[SearchHit]:
        """Return the best passages for a query, best first."""
        if self.is_empty or not query.strip():
            return []
        query_terms = tokenize(query)
        if not query_terms:
            return []
        query_vector = self.embedder.embed_query(query)
        lexical = self._lexical_scores(query_terms)
        hits: list[SearchHit] = []
        for position, chunk in enumerate(self.chunks):
            vector_score = max(0.0, self._dot(query_vector, self._vectors[position]))
            score = vector_weight * vector_score + lexical_weight * lexical[position]
            if score < min_score:
                continue
            hits.append(
                SearchHit(
                    chunk=chunk,
                    score=score,
                    vector_score=vector_score,
                    lexical_score=lexical[position],
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(1, top_k)]

    def stats(self) -> dict:
        """Index summary used by the admin API and the demo UI."""
        return {
            "documents": len({chunk.document for chunk in self.chunks}),
            "chunks": len(self.chunks),
            "terms": len(self._document_frequency),
            "dimension": self.embedder.dimension,
            "embedder": self.embedder.name,
            "built_at": self.built_at.isoformat(),
        }
