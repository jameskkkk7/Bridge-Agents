"""Retrieval-augmented generation: chunking, embeddings, index and knowledge base."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from bridge_agents.rag import (
    DEFAULT_KNOWLEDGE_DIR,
    Chunk,
    HashedEmbedder,
    KnowledgeBase,
    KnowledgeIndex,
    OpenAIEmbedder,
    format_context,
    format_context_blocks,
    format_tool_result,
    load_documents,
    sources_payload,
    split_markdown,
    tokenize,
)

WIDGET_DOC = """# Widget Pro

Widget Pro is the self-hosted support widget for product teams. It ships with
the activation console and the refund policy.

## Activation

Activate Widget Pro from Settings → Billing → Activate. Enter the licence key
from your purchase email and confirm; activation takes effect immediately.

## Refunds

Refund requests follow the 14-day policy. Contact support with the order id and
the purchase date to start a refund review.

## Limits

The demo plan allows three seats. Larger plans are configured with an
environment variable.
"""


def _write(path: Path, name: str, text: str) -> Path:
    target = path / name
    target.write_text(text, encoding="utf-8")
    return target


def _base(directory: Path, **kwargs) -> KnowledgeBase:
    options = {"top_k": 3, "min_score": 0.0}
    options.update(kwargs)
    return KnowledgeBase(directory, HashedEmbedder(), **options)


class TestChunking:
    def test_headings_become_citable_chunks(self) -> None:
        chunks = split_markdown(WIDGET_DOC, source="widget.md")
        headings = {chunk.heading for chunk in chunks}
        assert {"Activation", "Refunds", "Limits"} <= headings
        assert len({chunk.id for chunk in chunks}) == len(chunks)
        activation = next(chunk for chunk in chunks if chunk.heading == "Activation")
        assert activation.citation() == "Widget Pro — Activation"
        assert activation.document == "Widget Pro"
        assert activation.source == "widget.md"
        assert "licence key" in activation.text

    def test_long_sections_are_split(self) -> None:
        paragraph = "This sentence is repeated to make the section long enough. "
        text = "# Long\n\n## Body\n\n" + "\n\n".join([paragraph * 4] * 12)
        chunks = split_markdown(text, source="long.md", max_chars=400, overlap=60)
        assert len(chunks) > 1
        assert all(len(chunk.text) <= 800 for chunk in chunks)

    def test_document_without_headings_keeps_its_name(self) -> None:
        chunks = split_markdown("Just a flat note about refunds.", source="note.txt")
        assert len(chunks) == 1
        assert chunks[0].document == "note"
        assert chunks[0].heading == ""

    def test_load_documents_reads_supported_files_only(self, tmp_path: Path) -> None:
        _write(tmp_path, "widget.md", WIDGET_DOC)
        _write(tmp_path, "notes.txt", "plain text")
        _write(tmp_path, "image.png", "not text")
        chunks = load_documents(tmp_path)
        assert {chunk.source for chunk in chunks} == {"widget.md", "notes.txt"}


class TestTokenize:
    def test_ascii_terms_and_cjk_characters(self) -> None:
        terms = tokenize("Activate Widget Pro 激活流程")
        assert "activate" in terms and "widget" in terms
        assert "激" in terms and "活" in terms
        assert "激活" in terms

    def test_short_ascii_noise_is_dropped(self) -> None:
        assert "a" not in tokenize("a b c activate")


class TestHashedEmbedder:
    def test_deterministic_and_normalised(self) -> None:
        embedder = HashedEmbedder(128)
        first = embedder.embed_query("activate widget pro")
        second = HashedEmbedder(128).embed_query("activate widget pro")
        assert first == second
        assert len(first) == 128
        norm = sum(value * value for value in first) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_related_text_is_closer_than_unrelated_text(self) -> None:
        embedder = HashedEmbedder()
        query = embedder.embed_query("how do I activate the widget licence")

        def cosine(other: str) -> float:
            vector = embedder.embed_query(other)
            return sum(a * b for a, b in zip(query, vector, strict=False))

        related = cosine("Activate Widget Pro from Settings to confirm the licence key")
        unrelated = cosine("Refund requests follow the fourteen day policy")
        assert related > unrelated

    def test_empty_text_is_a_zero_vector(self) -> None:
        vector = HashedEmbedder(32).embed_query("")
        assert vector == [0.0] * 32


class TestOpenAIEmbedder:
    def test_posts_batches_and_reads_vectors(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            payload = json.loads(request.content)
            data = [
                {"object": "embedding", "index": index, "embedding": [0.1, 0.2, 0.3]}
                for index, _ in enumerate(payload["input"])
            ]
            return httpx.Response(200, json={"object": "list", "data": data})

        embedder = OpenAIEmbedder(
            base_url="http://embedding.test/v1",
            api_key="test-key",
            model="test-embedding",
            batch_size=2,
            transport=httpx.MockTransport(handler),
        )
        vectors = embedder.embed_documents(["one", "two", "three"])
        assert len(vectors) == 3
        assert embedder.dimension == 3
        assert len(requests) == 2
        assert requests[0].url.path == "/v1/embeddings"
        assert requests[0].headers["authorization"] == "Bearer test-key"
        embedder.close()


class TestKnowledgeIndex:
    def _index(self) -> KnowledgeIndex:
        chunks = split_markdown(WIDGET_DOC, source="widget.md")
        return KnowledgeIndex(chunks, HashedEmbedder())

    def test_ranks_the_relevant_section_first(self) -> None:
        hits = self._index().search("How do I activate Widget Pro?", top_k=3)
        assert hits
        assert hits[0].chunk.heading == "Activation"
        assert hits[0].score >= hits[-1].score

    def test_refund_question_finds_the_policy(self) -> None:
        hits = self._index().search("refund policy order id", top_k=3)
        assert hits and hits[0].chunk.heading == "Refunds"

    def test_min_score_can_filter_everything(self) -> None:
        assert self._index().search("activate widget", min_score=2.0) == []

    def test_empty_index_returns_nothing(self) -> None:
        index = KnowledgeIndex([], HashedEmbedder())
        assert index.is_empty
        assert index.search("anything") == []
        assert index.stats()["chunks"] == 0


class TestFormatting:
    def _hits(self):
        index = KnowledgeIndex(split_markdown(WIDGET_DOC, source="widget.md"), HashedEmbedder())
        return index.search("activate widget", top_k=2)

    def test_context_is_numbered_and_citable(self) -> None:
        context = format_context(self._hits())
        assert "Retrieved knowledge" in context
        assert "[1] Widget Pro — Activation" in context
        assert "cite" in context.lower()

    def test_context_respects_the_budget(self) -> None:
        entries = [{"citation": f"Doc {index}", "text": "word " * 200} for index in range(1, 6)]
        context = format_context_blocks(entries, max_chars=400)
        assert len(context) <= 420
        assert "[1]" in context
        assert "[2]" not in context

    def test_tool_result_uses_the_same_citations(self) -> None:
        result = format_tool_result(self._hits())
        assert result.startswith("[1] Widget Pro — Activation")

    def test_sources_payload_is_json_friendly(self) -> None:
        payload = sources_payload(self._hits())
        assert payload[0]["index"] == 1
        assert payload[0]["citation"] == "Widget Pro — Activation"
        assert isinstance(payload[0]["score"], float)
        assert payload[0]["preview"]


class TestKnowledgeBase:
    def test_directory_is_indexed_and_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "widget.md", WIDGET_DOC)
        base = _base(tmp_path)
        assert base.search("activate widget")[0].chunk.heading == "Activation"
        documents = base.documents()
        assert documents[0]["name"] == "widget.md"
        assert documents[0]["chunks"] > 0
        stats = base.stats()
        assert stats["documents"] == 1
        assert stats["chunks"] > 0
        assert stats["embedder"] == "hash"

    def test_empty_directory_is_safe(self, tmp_path: Path) -> None:
        base = _base(tmp_path / "missing")
        assert base.search("anything") == []
        assert base.documents() == []
        assert base.stats()["chunks"] == 0

    def test_save_and_delete_document(self, tmp_path: Path) -> None:
        base = _base(tmp_path)
        base.save_document("faq.md", b"# FAQ\n\n## Shipping\n\nShipping takes five days.")
        assert any(document["name"] == "faq.md" for document in base.documents())
        assert base.search("shipping days")[0].chunk.document == "FAQ"
        assert base.delete_document("faq.md") is True
        assert base.delete_document("faq.md") is False
        assert base.search("shipping days") == []

    def test_upload_validation(self, tmp_path: Path) -> None:
        base = _base(tmp_path)
        with pytest.raises(ValueError):
            base.save_document("evil.exe", b"MZ")
        with pytest.raises(ValueError):
            base.save_document("empty.md", b"   ")
        with pytest.raises(ValueError):
            base.save_document("binary.md", b"\xff\xfe\x00")

    def test_new_files_are_picked_up_by_the_signature(self, tmp_path: Path) -> None:
        base = _base(tmp_path)
        assert base.search("activation") == []
        _write(tmp_path, "widget.md", WIDGET_DOC)
        assert base.search("activation")[0].chunk.heading == "Activation"

    def test_seed_from_bundled_directory(self, tmp_path: Path) -> None:
        source = tmp_path / "bundled"
        source.mkdir()
        _write(source, "widget.md", WIDGET_DOC)
        target = tmp_path / "knowledge"
        base = _base(target)
        assert base.seed_from(source) == 1
        assert base.documents()[0]["name"] == "widget.md"
        # Seeding is idempotent: a populated directory is left alone.
        assert base.seed_from(source) == 0

    def test_default_knowledge_directory_constant(self) -> None:
        assert DEFAULT_KNOWLEDGE_DIR.startswith("./data")


class TestChunkModel:
    def test_chunk_dict_contains_citation_metadata(self) -> None:
        chunk = Chunk(
            id="doc#activation",
            document="Widget Pro",
            heading="Activation",
            text="Activate it.",
            source="doc.md",
        )
        payload = chunk.as_dict()
        assert payload["citation"] == "Widget Pro — Activation"
        assert payload["id"] == "doc#activation"
