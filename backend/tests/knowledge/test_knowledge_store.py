from datetime import date
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


def test_expired_source_is_excluded(tmp_path: Path) -> None:
    content = """<!--
destination: 杭州
source: old-guide.md
source_version: 2020-01-01
title: 旧攻略
-->
## 西湖
旧信息
"""
    (tmp_path / "old.md").write_text(content, encoding="utf-8")
    knowledge = KnowledgeBase.from_directory(tmp_path, as_of=date(2026, 1, 1), max_age_days=365)
    assert knowledge.search("杭州", "西湖") == []


def test_invalid_source_version_is_rejected(tmp_path: Path) -> None:
    content = """<!--
destination: 杭州
source: broken-guide.md
source_version: not-a-date
title: 错误版本
-->
## 西湖
内容
"""
    (tmp_path / "broken.md").write_text(content, encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="source_version"):
        KnowledgeBase.from_directory(tmp_path, as_of=date(2026, 1, 1))


def test_same_title_from_different_sources_can_coexist(tmp_path: Path) -> None:
    template = """<!--
destination: 杭州
source: {source}
source_version: 2026-01-01
title: 杭州攻略
-->
## 西湖
{text}
"""
    (tmp_path / "one.md").write_text(
        template.format(source="guide-one.md", text="第一来源"), encoding="utf-8"
    )
    (tmp_path / "two.md").write_text(
        template.format(source="guide-two.md", text="第二来源"), encoding="utf-8"
    )
    knowledge = KnowledgeBase.from_directory(tmp_path, as_of=date(2026, 1, 2))
    assert len(knowledge.chunks) == 2
    assert len({chunk.chunk_id for chunk in knowledge.chunks}) == 2
