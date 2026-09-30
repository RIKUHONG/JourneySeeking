from pathlib import Path

import pytest

from backend.app.knowledge import KnowledgeBase, KnowledgeBaseError

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"


def test_default_knowledge_base_has_reviewable_metadata() -> None:
    knowledge = KnowledgeBase.from_directory(DATA_DIR)
    assert {document.destination for document in knowledge.documents} == {"北京", "成都", "杭州"}
    assert all(chunk.source_version == "2026-09-30" for chunk in knowledge.chunks)
    assert all(chunk.source for chunk in knowledge.chunks)


def test_search_isolated_by_destination() -> None:
    knowledge = KnowledgeBase.from_directory(DATA_DIR)
    results = knowledge.search("杭州", "故宫 天安门", top_k=5)
    assert results == []
    assert all(result.destination == "杭州" for result in knowledge.search("杭州", "西湖", 5))


def test_search_ranks_title_match_and_respects_top_k() -> None:
    knowledge = KnowledgeBase.from_directory(DATA_DIR)
    results = knowledge.search("成都", "美食 火锅", top_k=1)
    assert len(results) == 1
    assert results[0].title == "地方美食"
    assert results[0].as_dict()["source_version"] == "2026-09-30"


def test_search_empty_query_or_unknown_destination_is_empty() -> None:
    knowledge = KnowledgeBase.from_directory(DATA_DIR)
    assert knowledge.search("杭州", "", 5) == []
    assert knowledge.search("上海", "西湖", 5) == []


def test_invalid_directory_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseError, match="没有 Markdown"):
        KnowledgeBase.from_directory(tmp_path)
