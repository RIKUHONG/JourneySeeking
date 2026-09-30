"""Schemas for reviewable travel knowledge sources and chunks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """A source document with stable provenance metadata."""

    destination: str
    source: str
    source_version: str
    title: str
    path: str


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A retrievable, cited section of a knowledge document."""

    chunk_id: str
    destination: str
    title: str
    text: str
    source: str
    source_version: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "destination": self.destination,
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "source_version": self.source_version,
            "tags": list(self.tags),
        }
