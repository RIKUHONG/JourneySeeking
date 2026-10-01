# P2-03 攻略知识库与检索

## 当前实现

知识源位于 `backend/data/knowledge/`，每个 Markdown 文件必须以 HTML 注释保存以下元数据：

- `destination`：规范城市名
- `source`：来源名称或来源标识
- `source_version`：可审阅的版本号或日期
- `title`：文档标题

文档使用二级标题切分为可检索片段。`KnowledgeBase` 在加载时检查元数据、空文档和重复 `chunk_id`；检索结果始终带 `destination`、`source`、`source_version`，可直接交给 P2-07 编排和 Critic。

`source_version` 必须是 `YYYY-MM-DD`。默认以当前日期为基准，只加载最近 365 天内的版本；未来日期和超过有效期的文档都会被排除。测试或离线评估可传入固定 `as_of` 和 `max_age_days`，保证结果可复现。

当前首批城市为杭州、北京、成都。现有条目是项目内可审阅的策划知识，不代表实时营业时间、价格、客流或 POI 已核实；这些事实仍须由地图、天气或其他实时 integration 提供。

## 检索策略

第一版使用确定性关键词检索：标题命中权重高于正文，结果只在指定城市内搜索，空查询、未知城市和无命中返回空列表。`top_k` 控制结果数量，不会跨城市补结果，也不依赖外部模型、密钥或向量数据库。

```python
from backend.app.knowledge import load_default_knowledge_base

knowledge = load_default_knowledge_base()
chunks = knowledge.search("杭州", "西湖 慢游", top_k=3)
```

知识库不可用时，调用方应记录降级原因并继续基础行程链路；不能把没有来源的模型文本标记为攻略命中。

## 离线评估

在仓库根目录运行：

```powershell
python -m backend.scripts.evaluate_rag
```

评估集位于 `backend/eval/rag_eval_cases.json`，包含正例、空命中和跨城负例。脚本输出正例 Top-K 命中率、整体用例通过率和跨城市污染率；正例命中率低于 80% 或污染率高于 0% 时返回非零退出码。

截至 2026-10-01，运行 `python -m backend.scripts.evaluate_rag` 的基线为：

```text
positive_top_k_hit_rate: 4/4 (100.0%)
overall_case_pass_rate: 7/7 (100.0%)
cross_destination_pollution_rate: 0/9 (0.0%)
evaluation_status: PASS
```

新增城市、来源或修改检索规则时，应同步更新评估集并在 PR 中记录基线变化。
