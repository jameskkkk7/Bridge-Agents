"""Embedding back ends used by the retrieval index.

Two implementations share one protocol:

* :class:`HashedEmbedder` is deterministic and offline. It hashes word and
  character n-grams into a fixed number of buckets with signed weights, so the
  same text always produces the same vector on every machine and in every
  process (Python's built-in ``hash`` is deliberately not used).
* :class:`OpenAIEmbedder` calls any OpenAI-compatible ``/v1/embeddings``
  endpoint, which is what a production deployment should use.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import Protocol

import httpx

from bridge_agents.rag.documents import stem, tokenize

DEFAULT_DIMENSION = 256
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class Embedder(Protocol):
    """Turns text into a numeric vector for similarity search."""

    name: str
    dimension: int

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed many documents at once."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query."""


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class HashedEmbedder:
    """Deterministic hashed bag-of-terms embedding (no model download)."""

    name = "hash"

    def __init__(self, dimension: int = DEFAULT_DIMENSION) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self.dimension = dimension

    def _bucket(self, term: str) -> tuple[int, float]:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dimension
        sign = 1.0 if (value >> 63) & 1 else -1.0
        return index, sign

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        terms = tokenize(text)
        if not terms:
            return vector
        counts: dict[str, int] = {}
        for term in terms:
            key = stem(term)
            counts[key] = counts.get(key, 0) + 1
        for term, count in counts.items():
            index, sign = self._bucket(term)
            # Sublinear term frequency keeps repeated boilerplate from dominating.
            vector[index] += sign * (1.0 + math.log(count))
        return _normalise(vector)

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAIEmbedder:
    """Embeddings from an OpenAI-compatible endpoint."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        timeout: float = 30.0,
        batch_size: int = 64,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self._transport = transport
        self._client = client
        self.dimension = 0

    @property
    def model(self) -> str:
        return self._model

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
            transport=self._transport,
        )
        return self._client

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        response = self._http().post(
            "/embeddings",
            json={"model": self._model, "input": batch},
        )
        response.raise_for_status()
        payload = response.json()
        vectors = [item["embedding"] for item in payload.get("data", [])]
        if len(vectors) != len(batch):
            raise ValueError("embedding endpoint returned the wrong number of vectors")
        self.dimension = len(vectors[0]) if vectors else self.dimension
        return [list(map(float, vector)) for vector in vectors]

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        items = list(texts)
        vectors: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            vectors.extend(self._embed_batch(items[start : start + self._batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
