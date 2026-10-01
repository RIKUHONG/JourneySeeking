from pathlib import Path

import pytest

from backend.app.knowledge import KnowledgeBase, KnowledgeBaseError


def test_duplicate_chunk_ids_are_rejected(tmp_path: Path) -> None:
    content = """<!--
destination: 杭州
source: test
source_version: 2026-01-01
title: 测试
-->
## 同一节
西湖
"""
    (tmp_path / "one.md").write_text(content, encoding="utf-8")
    (tmp_path / "two.md").write_text(content, encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="chunk_id 重复"):
        KnowledgeBase.from_directory(tmp_path)


def test_missing_metadata_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("# no metadata\ntext", encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="缺少元数据"):
        KnowledgeBase.from_directory(tmp_path)


def test_same_source_and_same_section_is_rejected(tmp_path: Path) -> None:
    content = """<!--
destination: 杭州
source: same-guide.md
source_version: 2026-01-01
title: 测试
-->
## 同一节
西湖
"""
    (tmp_path / "one.md").write_text(content, encoding="utf-8")
    (tmp_path / "two.md").write_text(content, encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="chunk_id 重复"):
        KnowledgeBase.from_directory(tmp_path)
