"""Runtime knowledge base: directory scanning, seeding, indexing and lookup.

The base is process-wide and rebuilt lazily. A missing or empty knowledge
directory yields an empty index rather than an error, so a deployment without a
knowledge base still answers (the retrieval node simply passes through).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from bridge_agents.config import Settings, get_settings
from bridge_agents.rag.documents import (
    _SUPPORTED_SUFFIXES,
    Chunk,
    load_documents,
)
from bridge_agents.rag.embeddings import (
    DEFAULT_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    Embedder,
    HashedEmbedder,
    OpenAIEmbedder,
)
from bridge_agents.rag.index import DEFAULT_MIN_SCORE, DEFAULT_TOP_K, KnowledgeIndex, SearchHit

LOGGER = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE_DIR = "./data/knowledge"
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def build_embedder(settings: Settings) -> Embedder:
    """Create the embedder selected by ``RAG_EMBEDDER``."""
    kind = (settings.rag_embedder or "hash").strip().lower()
    if kind == "openai":
        return OpenAIEmbedder(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.rag_embedding_model or DEFAULT_EMBEDDING_MODEL,
            timeout=float(settings.openai_timeout),
        )
    return HashedEmbedder(DEFAULT_DIMENSION)


class KnowledgeBase:
    """One directory of markdown/text documents, indexed for hybrid search."""

    def __init__(
        self,
        directory: Path,
        embedder: Embedder,
        *,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
        max_context_chars: int = 2400,
    ) -> None:
        self.directory = Path(directory).expanduser()
        self.embedder = embedder
        self.top_k = max(1, top_k)
        self.min_score = min_score
        self.chunk_size = max(200, chunk_size)
        self.chunk_overlap = max(0, chunk_overlap)
        self.max_context_chars = max_context_chars
        self._index = KnowledgeIndex([], embedder)
        self._signature: tuple = ()
        self._built_documents = 0

    # -- lifecycle ----------------------------------------------------------

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return [
            path
            for path in sorted(self.directory.iterdir())
            if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES
        ]

    def _current_signature(self) -> tuple:
        parts: list[tuple] = []
        for path in self._files():
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append((path.name, stat.st_mtime_ns, stat.st_size))
        return tuple(parts)

    def _load_chunks(self) -> list[Chunk]:
        return load_documents(
            self.directory,
            max_chars=self.chunk_size,
            overlap=self.chunk_overlap,
        )

    def reload(self, *, force: bool = False) -> bool:
        """Rebuild the index when the directory changed; returns True if rebuilt."""
        signature = self._current_signature()
        if not force and signature == self._signature and self._built_documents == len(signature):
            return False
        chunks = self._load_chunks()
        self._index = KnowledgeIndex(chunks, self.embedder)
        self._signature = signature
        self._built_documents = len(signature)
        LOGGER.info(
            "knowledge base indexed: %d documents, %d chunks (%s embedder)",
            len({chunk.document for chunk in chunks}),
            len(chunks),
            self.embedder.name,
        )
        return True

    def close(self) -> None:
        """Release the embedder's HTTP client, when it has one."""
        closer = getattr(self.embedder, "close", None)
        if callable(closer):
            closer()

    # -- queries ------------------------------------------------------------

    @property
    def index(self) -> KnowledgeIndex:
        self.reload()
        return self._index

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[SearchHit]:
        """Search the current index; empty when the directory has no documents."""
        return self.index.search(
            query,
            top_k=top_k or self.top_k,
            min_score=self.min_score if min_score is None else min_score,
        )

    # -- reporting ----------------------------------------------------------

    def documents(self) -> list[dict]:
        """Document list with size and per-document chunk counts."""
        counts: dict[str, int] = {}
        for chunk in self.index.chunks:
            counts[chunk.source] = counts.get(chunk.source, 0) + 1
        entries: list[dict] = []
        for path in self._files():
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": path.name,
                    "bytes": stat.st_size,
                    "modified": stat.st_mtime,
                    "chunks": counts.get(path.name, 0),
                }
            )
        return entries

    def stats(self) -> dict:
        """Full status payload for the admin API and the demo UI."""
        index_stats = self.index.stats()
        return {
            **index_stats,
            "directory": str(self.directory),
            "files": len(self._files()),
            "top_k": self.top_k,
            "min_score": self.min_score,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }

    # -- maintenance --------------------------------------------------------

    def save_document(self, name: str, content: bytes) -> Path:
        """Store one uploaded document and rebuild the index."""
        suffix = Path(name).suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            raise ValueError("Only markdown and text documents are supported")
        safe_name = Path(name).name
        if not safe_name or safe_name.startswith("."):
            raise ValueError("Invalid document name")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError("The document is too large")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("The document must be UTF-8 text") from exc
        if not text.strip():
            raise ValueError("The document is empty")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / safe_name
        target.write_text(text, encoding="utf-8")
        self.reload(force=True)
        return target

    def read_document(self, name: str) -> dict:
        """Return one document's metadata and full text for the Studio preview."""
        safe_name = Path(name).name
        if (
            not safe_name
            or safe_name.startswith(".")
            or Path(safe_name).suffix.lower() not in _SUPPORTED_SUFFIXES
        ):
            raise ValueError("Unsupported document name")
        target = self.directory / safe_name
        if not target.is_file():
            raise FileNotFoundError(safe_name)
        stat = target.stat()
        chunks = next(
            (entry["chunks"] for entry in self.documents() if entry["name"] == safe_name), 0
        )
        return {
            "name": safe_name,
            "bytes": stat.st_size,
            "modified": stat.st_mtime,
            "chunks": chunks,
            "content": target.read_text(encoding="utf-8"),
        }

    def delete_document(self, name: str) -> bool:
        """Remove one document and rebuild the index."""
        target = self.directory / Path(name).name
        if not target.is_file() or target.suffix.lower() not in _SUPPORTED_SUFFIXES:
            return False
        target.unlink()
        self.reload(force=True)
        return True

    def seed_from(self, source: Path) -> int:
        """Copy bundled documents into an empty knowledge directory."""
        self.directory.mkdir(parents=True, exist_ok=True)
        if self._files():
            return 0
        if not source.is_dir():
            return 0
        copied = 0
        for path in sorted(source.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
                continue
            shutil.copyfile(path, self.directory / path.name)
            copied += 1
        if copied:
            LOGGER.info("seeded %d knowledge document(s) from %s", copied, source)
            self.reload(force=True)
        return copied


def _bundled_docs_directory() -> Path:
    """Best-effort location of the documentation bundle shipped with the repo.

    The server image copies ``docs/kb`` next to the working directory; an
    installed wheel has no bundle, in which case seeding is simply skipped.
    """
    working_copy = Path.cwd() / "docs" / "kb"
    if working_copy.is_dir():
        return working_copy
    return Path(__file__).resolve().parents[5] / "docs" / "kb"


def build_knowledge(settings: Settings | None = None) -> KnowledgeBase:
    """Build a knowledge base from application settings."""
    config = settings or get_settings()
    directory = Path(config.knowledge_dir or DEFAULT_KNOWLEDGE_DIR)
    source = Path(config.docs_dir) if config.docs_dir else _bundled_docs_directory()
    base = KnowledgeBase(
        directory,
        build_embedder(config),
        top_k=config.rag_top_k,
        min_score=config.rag_min_score,
        chunk_size=config.rag_chunk_size,
        chunk_overlap=config.rag_chunk_overlap,
        max_context_chars=config.rag_max_context_chars,
    )
    base.seed_from(source)
    return base


_knowledge: KnowledgeBase | None = None
_knowledge_key: tuple | None = None


def _settings_key(settings: Settings) -> tuple:
    return (
        settings.knowledge_dir,
        settings.docs_dir,
        settings.rag_embedder,
        settings.rag_embedding_model,
        settings.openai_base_url,
        settings.openai_timeout,
        settings.rag_top_k,
        settings.rag_min_score,
        settings.rag_chunk_size,
        settings.rag_chunk_overlap,
        settings.rag_max_context_chars,
    )


def get_knowledge() -> KnowledgeBase:
    """Return the process-wide knowledge base, rebuilding it when settings change."""
    global _knowledge, _knowledge_key
    settings = get_settings()
    key = _settings_key(settings)
    if _knowledge is None or _knowledge_key != key:
        if _knowledge is not None:
            _knowledge.close()
        _knowledge = build_knowledge(settings)
        _knowledge_key = key
    return _knowledge


def reset_knowledge() -> None:
    """Drop the cached knowledge base (used by tests and after configuration changes)."""
    global _knowledge, _knowledge_key
    if _knowledge is not None:
        _knowledge.close()
    _knowledge = None
    _knowledge_key = None


def refresh_knowledge() -> KnowledgeBase:
    """Force a rebuild of the cached knowledge base and return it."""
    base = get_knowledge()
    base.reload(force=True)
    return base
