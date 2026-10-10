# 架构现状与 P2 演进

状态基线：2026-10-08 本地 `main` 已包含 P2-01～P2-03。当前代码只有后端：`backend/app/main.py` 提供 HTTP 路由，`models/schemas.py` 定义旅行和版本契约，`services/` 完成生成、候选、地图和天气补全，`integrations/` 封装 MoMA/高德，`cache/` 提供内存实现，`storage/` 提供 SQLite 行程版本存储。测试在 `backend/tests/`。`frontend/`、RAG 以外的 Agent 编排和导出尚未建立。

```text
POST /api/trip/generate
  -> TripService -> ItineraryGenerator -> MoMA
                 -> MapEnrichmentService -> MapService / MemoryCache
                 -> WeatherEnrichmentService -> WeatherService
  -> Itinerary
```

地图/天气补全只处理通过基础校验的行程。候选池先由城市解析服务归一化目的地，再过滤跨城、无坐标或无 ID 的供应商结果，并检查景点/餐饮/住宿最低数量；候选不足或地图不可用时回退到基础生成，不伪造 POI。没有可靠 POI 时不填供应商 ID/坐标；没有可靠起终点时不伪造路线；预报按日期匹配，超出供应商范围为 `unknown`。外部补全失败时保留基础行程。`/api/chat` 是原始 MoMA 消息转发，不持有旅行会话。

## P2 分层约束

- HTTP 层处理输入输出、错误码和依赖注入；不直接实现 Prompt、业务规则或数据库操作。
- service 层持有行程版本、局部编辑、编排、Critic 和降级规则；所有修改最终经过 `Itinerary` 与跨字段校验。
- integration 层继续封装 MoMA、高德等外部服务；RAG 检索返回带来源的片段，不能把攻略文本当实时营业/价格事实。
- 存储层保存完整行程版本，供编辑、历史和导出共用；缓存层只加速可重建数据，不保存唯一业务事实。
- 当前 SQLite 存储使用 `TRIP_DATABASE_PATH` 配置，保存 `trips` 当前版本索引和不可变的 `trip_versions` 快照；版本写入使用 `expected_version` 条件更新，后续生产迁移应保持同一仓储协议和冲突语义。
- 前端以 `docs/api-contract.md` 与 OpenAPI 为准；天气与 POI 的真实性状态由后端提供。

目标依赖方向为 `前端 → HTTP → services → integrations / storage / cache`。成员 A 的 P2-01 先定义身份与版本契约，其余任务按 [P2 Issue 清单](p2-issues.md) 的 A/B/C 边界接入。Redis 与天气自动调度是条件任务，不是当前运行链路。

P2-06 的 `SessionService` 和 `SQLiteSessionRepository` 使用与行程版本相同的 SQLite 文件，但使用独立的 `trip_sessions` 表。会话只保存 `trip_id`、`current_version`、TTL、摘要和有界的近期指令；完整行程始终从 `TripRepository` 读取。会话编辑调用 P2-05 的 `TripEditService`，不复制局部差异、费用、POI 或路线校验。
