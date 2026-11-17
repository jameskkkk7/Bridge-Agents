"""Document loading and heading-aware chunking for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")
_SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
_DEFAULT_MAX_CHARS = 900
_DEFAULT_OVERLAP = 120

# Question words and glue words carry no retrieval signal and add noise to both
# the lexical score and the hashed embedding, so they are dropped while
# tokenizing. CJK terms are never filtered by this list.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def is_supported_document(path: Path) -> bool:
    """True when the file is a knowledge document this loader understands."""
    return path.suffix.lower() in _SUPPORTED_SUFFIXES and path.is_file()


def tokenize(text: str, *, min_length: int = 2, bigrams: bool = True) -> list[str]:
    """Split text into lowercase terms, including CJK characters and bigrams.

    ASCII words shorter than ``min_length`` are dropped; CJK text has no word
    boundaries that a regex can find, so each character and each character pair
    becomes a term. Common English stopwords are removed, which keeps question
    phrasing from diluting the retrieval score. The same function is used for
    indexing and querying, so lexical scoring stays symmetric.
    """
    lowered = text.lower()
    terms: list[str] = [
        word
        for word in _TOKEN_PATTERN.findall(lowered)
        if len(word) >= min_length and word not in _STOPWORDS
    ]
    for run in _CJK_PATTERN.findall(lowered):
        terms.extend(run)
        if bigrams and len(run) > 1:
            terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return terms


# Light suffix stripping so "activate", "activated" and "activation" share a
# term. This is intentionally not a full stemmer: the retrieval corpus is small
# product documentation, and a deterministic rule set is easier to reason about.
_STEM_SUFFIXES = ("ational", "ation", "ings", "ing", "ers", "er", "ed", "es", "s")


def stem(term: str) -> str:
    """Return a coarse English stem used for lexical matching and embeddings."""
    for suffix in _STEM_SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 4:
            term = term[: -len(suffix)]
            break
    if term.endswith("ion") and len(term) >= 6:
        term = term[:-3]
    if len(term) >= 5 and term.endswith("e"):
        term = term[:-1]
    if len(term) >= 5 and term.endswith("at"):
        term = term[:-2]
    return term


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrievable passage and its citation metadata."""

    id: str
    document: str
    heading: str
    text: str
    source: str

    def citation(self) -> str:
        """Human-readable citation used in prompts and tool output."""
        if self.heading:
            return f"{self.document} — {self.heading}"
        return self.document

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "document": self.document,
            "heading": self.heading,
            "source": self.source,
            "text": self.text,
            "citation": self.citation(),
        }


def document_title(text: str, fallback: str) -> str:
    """Return the first level-one heading, or a filename-derived fallback."""
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return fallback


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:48] or "section"


def _paragraphs(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text)]
    return [block for block in blocks if block]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split a section into overlapping paragraph groups."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in _paragraphs(text):
        if current and size + len(paragraph) + 2 > max_chars:
            pieces.append("\n\n".join(current))
            tail = current[-1] if current else ""
            current = [tail] if overlap and tail else []
            size = len(tail) + 2 if tail else 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def split_markdown(
    text: str,
    *,
    source: str,
    display_name: str | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split one document into heading-aware, size-bounded chunks.

    Every heading starts a new chunk; long sections are split again on paragraph
    boundaries with a small overlap so an answer is not cut in half. A document
    without headings becomes chunks of plain text named after the file.
    """
    title = document_title(text, display_name or Path(source).stem)
    sections: list[tuple[str, str]] = []
    current_heading = ""
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append((current_heading, body))

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            current_heading = match.group(2).strip()
            buffer = []
            continue
        buffer.append(line)
    flush()

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for heading, body in sections:
        for piece in _split_long(body, max_chars, overlap):
            label = heading or title
            slug = _slug(label)
            seen[slug] = seen.get(slug, 0) + 1
            suffix = f"-{seen[slug]}" if seen[slug] > 1 else ""
            chunks.append(
                Chunk(
                    id=f"{source}#{slug}{suffix}",
                    document=title,
                    heading=heading if heading != title else "",
                    text=piece,
                    source=source,
                )
            )
    return chunks


def load_documents(
    directory: Path,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP,
    suffixes: frozenset[str] = _SUPPORTED_SUFFIXES,
) -> list[Chunk]:
    """Load and chunk every supported document in a directory (non-recursive)."""
    if not directory.is_dir():
        return []
    chunks: list[Chunk] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        chunks.extend(
            split_markdown(
                text,
                source=path.name,
                display_name=path.stem,
                max_chars=max_chars,
                overlap=overlap,
            )
        )
    return chunks
