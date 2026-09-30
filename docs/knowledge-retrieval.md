# P2-03 攻略知识库与检索

## 当前实现

知识源位于 `backend/data/knowledge/`，每个 Markdown 文件必须以 HTML 注释保存以下元数据：

- `destination`：规范城市名
- `source`：来源名称或来源标识
- `source_version`：可审阅的版本号或日期
- `title`：文档标题

文档使用二级标题切分为可检索片段。`KnowledgeBase` 在加载时检查元数据、空文档和重复 `chunk_id`；检索结果始终带 `destination`、`source`、`source_version`，可直接交给 P2-07 编排和 Critic。

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

评估集位于 `backend/eval/rag_eval_cases.json`，当前输出 Top-K 命中率和跨城市污染数。新增城市或修改知识源时，应同步更新评估集并在 PR 中记录基线变化。
