"""Load and search the reviewable Markdown knowledge base."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date
from pathlib import Path

from .models import KnowledgeChunk, KnowledgeDocument


class KnowledgeBaseError(RuntimeError):
    """Raised when the knowledge base cannot be loaded or is invalid."""


DEFAULT_MAX_AGE_DAYS = 365
_METADATA_RE = re.compile(r"\A<!--\s*(.*?)\s*-->", re.DOTALL)
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z][a-zA-Z0-9_-]{1,}")


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(value):
        if all("\u4e00" <= char <= "\u9fff" for char in token):
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token.casefold())
    return tokens


def parse_source_version(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise KnowledgeBaseError("source_version 必须是 YYYY-MM-DD 日期") from exc


def is_fresh(value: str, *, as_of: date, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
    if max_age_days < 0:
        raise ValueError("max_age_days 不能为负数")
    version_date = parse_source_version(value)
    age_days = (as_of - version_date).days
    return 0 <= age_days <= max_age_days


def _parse_header(text: str, path: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("<!--"):
        raise KnowledgeBaseError(f"知识文档缺少元数据注释：{path.name}")
    match = _METADATA_RE.match(text)
    if not match:
        raise KnowledgeBaseError(f"知识文档元数据格式错误：{path.name}")
    metadata: dict[str, str] = {}
    for item in match.group(1).splitlines():
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        metadata[key.strip()] = value.strip()
    body = text[match.end() :].strip()
    required = ("destination", "source", "source_version", "title")
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise KnowledgeBaseError(f"{path.name} 缺少元数据：{', '.join(missing)}")
    return metadata, body


def _chunk_document(document: KnowledgeDocument, body: str) -> list[KnowledgeChunk]:
    sections: list[tuple[str, list[str]]] = []
    current_title = document.title
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if "\n".join(current_lines).strip():
                sections.append((current_title, current_lines))
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# ") and not current_lines:
            current_title = line[2:].strip() or document.title
        else:
            current_lines.append(line)
    if "\n".join(current_lines).strip():
        sections.append((current_title, current_lines))

    chunks: list[KnowledgeChunk] = []
    source_name = Path(document.source).stem or Path(document.path).stem
    source_hash = hashlib.sha256(document.source.encode("utf-8")).hexdigest()[:10]
    document_id = f"{source_name}-{source_hash}"
    for index, (title, lines) in enumerate(sections, start=1):
        content = "\n".join(lines).strip()
        if not content:
            continue
        tags = tuple(dict.fromkeys(_tokens(f"{title} {content}")))
        chunk_id = f"{document.destination}:{document_id}:{title}:{index}"
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                destination=document.destination,
                title=title,
                text=content,
                source=document.source,
                source_version=document.source_version,
                tags=tags,
            )
        )
    return chunks


class KnowledgeBase:
    """In-memory deterministic retriever with explicit destination isolation."""

    def __init__(self, documents: list[KnowledgeDocument], chunks: list[KnowledgeChunk]) -> None:
        self.documents = tuple(documents)
        self.chunks = tuple(chunks)
        self._by_destination = {
            destination: tuple(chunk for chunk in self.chunks if chunk.destination == destination)
            for destination in {chunk.destination for chunk in self.chunks}
        }

    @classmethod
    def from_directory(
        cls,
        directory: Path,
        *,
        as_of: date | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> KnowledgeBase:
        as_of = as_of or date.today()  # noqa: DTZ011 - date-only freshness policy
        if not directory.exists():
            raise KnowledgeBaseError(f"知识库目录不存在：{directory}")
        documents: list[KnowledgeDocument] = []
        chunks: list[KnowledgeChunk] = []
        paths = sorted(directory.glob("*.md"))
        if not paths:
            raise KnowledgeBaseError(f"知识库目录没有 Markdown 文档：{directory}")
        for path in paths:
            metadata, body = _parse_header(path.read_text(encoding="utf-8"), path)
            document = KnowledgeDocument(
                destination=metadata["destination"],
                source=metadata["source"],
                source_version=metadata["source_version"],
                title=metadata["title"],
                path=str(path),
            )
            if not is_fresh(document.source_version, as_of=as_of, max_age_days=max_age_days):
                continue
            document_chunks = _chunk_document(document, body)
            if not document_chunks:
                raise KnowledgeBaseError(f"知识文档没有可检索内容：{path.name}")
            documents.append(document)
            chunks.extend(document_chunks)
        cls._validate(documents, chunks)
        return cls(documents, chunks)

    @staticmethod
    def _validate(documents: list[KnowledgeDocument], chunks: list[KnowledgeChunk]) -> None:
        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise KnowledgeBaseError("知识片段 chunk_id 重复")
        destinations = {doc.destination for doc in documents}
        if any(chunk.destination not in destinations for chunk in chunks):
            raise KnowledgeBaseError("知识片段引用了未登记目的地")

    @property
    def destinations(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_destination))

    def search(self, destination: str, query: str, top_k: int = 5) -> list[KnowledgeChunk]:
        """Return cited chunks ranked by deterministic lexical relevance."""
        if not destination.strip() or not query.strip() or top_k <= 0:
            return []
        candidates = self._by_destination.get(destination.strip(), ())
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored: list[tuple[float, int, KnowledgeChunk]] = []
        for index, chunk in enumerate(candidates):
            title_counts = Counter(_tokens(chunk.title))
            text_counts = Counter(_tokens(chunk.text))
            matched = sum(
                1 for token in query_tokens if token in title_counts or token in text_counts
            )
            if matched == 0:
                continue
            score = sum(4 * title_counts[token] + text_counts[token] for token in query_tokens)
            score += matched / len(set(query_tokens))
            scored.append((score, -index, chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [chunk for _, _, chunk in scored[:top_k]]

    def search_dicts(self, destination: str, query: str, top_k: int = 5) -> list[dict[str, object]]:
        return [chunk.as_dict() for chunk in self.search(destination, query, top_k)]


DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"


def load_default_knowledge_base(
    *, as_of: date | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> KnowledgeBase:
    return KnowledgeBase.from_directory(
        DEFAULT_KNOWLEDGE_DIR, as_of=as_of, max_age_days=max_age_days
    )
