# P3-02 天气前置与 7 天窗口任务流程

状态：P3-02 已实现，离线验收与真实联调通过。范围和总验收门槛以 [P3 规划](p3-plan.md) 为准；本文件只细化 P3-02，不启动 P3-03 Prompt 注册表、P3-04 MCP 或天气驱动的已保存行程重规划。

## 当前基线和关键约束

- P3-01 已提供 `query_weather_7d -> join_planning_context -> generate_base_itinerary -> apply_authoritative_weather`，天气和 POI 搜索位于基础生成前；`AGENT_RUNTIME=legacy` 仍走 P2 后置补全。
- `WeatherClient.forecast_window(start_date, end_date)` 已使用 Open-Meteo 指定日期范围接口，支持 1 至 7 天；图节点按请求日期查询，legacy 后置补全也使用同一来源。
- 高德天气接口实测只有当前起 4 天且忽略后续日期参数，因此不再用于天气事实；高德地理编码仅提供城市坐标。
- `DailyForecast` 保留日期、天气和温度，并新增可选 `source`、`fetched_at`；图状态与最终 `DayPlan.weather` 均保留 Open-Meteo 来源及适配器获取时间。

## 前置可行性实测（2026-10-13）

在本地已有密钥下以杭州行政区码 `330100` 查询，记录中不包含密钥或供应商原始响应：

| 请求 | 返回日期 | 结论 |
| --- | --- | --- |
| 高德 `/weather/weatherInfo`，`extensions=all` | 10 月 13 至 16 日，共 4 天 | 当前接口只给出这 4 个日历日。 |
| 同一接口额外传入 `start_date=2026-10-17&end_date=2026-10-19` | 仍为 10 月 13 至 16 日 | 该参数没有实现可寻址的后续窗口，不能靠重复调用得到第 5 至 7 天。 |
| 高德地理编码坐标 + Open-Meteo 日期范围接口 | 10 月 13 至 19 日，以及 10 月 14 至 20 日，两次均连续 7 天 | 技术上存在可用的 7 日数据源。 |

Open-Meteo 官方 [README](https://github.com/open-meteo/open-meteo#readme) 将免费 API 描述为非商业用途，数据要求 CC BY 4.0 来源标注。项目按非商业用途使用，页面展示 Open-Meteo 来源链接。

实施决定：天气事实统一使用 Open-Meteo。一次请求覆盖最多 7 天，无需高德天气分片；地理编码失败、Open-Meteo 超时或预报缺日时仍按日期标记 `unknown`，不伪造事实。

## 执行顺序

### 1. 冻结日期窗口和证据契约

1. 明确 `WeatherService` 的日期范围方法：城市、`start_date`、`end_date`，闭区间 1 至 7 个日历日；保留旧 `forecast(days)` 供 legacy 路径使用。超出窗口、倒序日期和空城市在调用外部服务前拒绝。
2. 窗口接口返回已校验的逐日记录；图节点以日期键补齐 `unknown` 并记录部分覆盖。每条可用记录保留日期、`source`、实际适配器获取时间 `fetched_at`；不得从模型或示例时间推断。
3. 约定重复日期的确定性处理、越界日期过滤、城市归属校验、单条无效记录和整次请求错误的处理。相同日期只能有一条可信证据，冲突记录不能随返回顺序覆盖。
4. 将高德 4 日上限与 Open-Meteo 7 日实测结果固化到契约；天气来源更换不改变 HTTP 字段、错误码或 SQLite 版本。

交付：更新 `docs/weather-contract.md` 中的日期窗口、来源、降级和供应商能力说明；仅在状态字段或图节点契约改变时更新 `docs/orchestration.md` 和图版本。

### 2. 实现适配器窗口能力

1. 在 `backend/app/integrations/contracts.py`、`weather_client.py` 与 `mock_weather_service.py` 增加日期范围接口；fake 可以返回部分覆盖。高德地理编码只取目标城市坐标，跨城市坐标拒绝。
2. 以坐标向 Open-Meteo 请求指定日期范围的逐日天气代码、最低/最高温度，映射为中文天气描述；只保留请求范围内的可信日期，不用邻近日补齐。
3. 按日期去重；冲突日期、不认识的天气代码、无效温度和越界日期不能成为事实。一次调用最多 7 天，超时和供应商错误使用脱敏错误码。
4. 不让异常原文、Key 或供应商原始响应进入 trace 或 Planner；失败时保留已校验行程并清除模型自报天气。

交付：适配器、fake 服务和仅依赖本地 `httpx.MockTransport` 的集成测试。

### 3. 接入生成前天气与后置权威回填

1. `backend/app/services/langgraph_orchestration.py` 始终通过日期范围接口查询请求的 3 至 7 天；检查并保留每个日期的 `available`/`unknown`、来源与获取时间。部分覆盖和超时在 `planning_context_status.weather`、trace 中标记降级。
2. `join_planning_context` 将逐日证据和降级状态送达 Planner。检查 `backend/app/services/prompt_builder.py` 的指令：有雨/恶劣天气证据时可以调整室内外活动和时段；`unknown` 不得推断晴天；用户日期、预算和可信 POI 白名单优先。
3. 结构校验之后只按 `DayPlan.date` 做权威天气回填和后端建议；模型自报的状况、温度和来源一律不能成为事实。Critic 复核 `unknown` 不含事实、可用记录与同日证据一致；冲突不能返回未校验行程。
4. legacy 仍使用后置天气补全和 `AGENT_RUNTIME=legacy` 回滚路径，但天气数据也来自 Open-Meteo；不修改 HTTP 字段或 SQLite 版本语义。

交付：图节点、Planner 输入、回填/Critic 的针对性修改与测试；不在 P3-02 建立完整 Prompt 注册表。

### 4. 离线验收矩阵

| 场景 | 必须验证的结果 |
| --- | --- |
| 3 天全覆盖 | 生成前取得 3 个日期；Planner 收到证据；回填与供应商逐日一致。 |
| 4 天全覆盖 | 指定起止日期一次查询 4 天，与请求日期一一对应。 |
| 7 天全覆盖 | Open-Meteo 一次返回 7 个可信日期；来源、获取时间在 Planner 和回填中一致。 |
| 7 天部分覆盖 | 缺失日恰为 `unknown`，无天气事实和建议；其余日期仍可用，trace 有 `partial_coverage`。 |
| 全部 unknown/无配置/超时 | Planner 收到 `degraded`，继续生成稳健安排；最终不出现伪造温度、天气或来源。 |
| 乱序、重复、越界、跨城市和无效记录 | 不发生错日绑定；冲突/不可信记录被拒绝或明确降级。 |
| 模型天气与证据冲突 | 回填恢复供应商事实；Critic 拒绝最终仍与证据不一致的行程。 |
| 回归与回滚 | POI 先于生成、修复上限、结构/Critic 硬门槛不变；legacy 和 langgraph 的 HTTP/版本契约均通过。 |

测试位置：`backend/tests/integrations/test_weather_client.py`、`test_mocks.py`、`backend/tests/api/test_langgraph_orchestration.py`、`test_weather_enrichment.py`，必要时补 `test_orchestration.py` 和 API/e2e fixture。先运行针对性测试，再运行后端全量测试和 lint。

### 5. 联调与验收记录

1. 用离线 fake 覆盖 3、4、7 天、部分覆盖和降级矩阵；真实联调运行 3 日 `langgraph` 与 7 日 Open-Meteo 适配器，保存脱敏节点路径，证明 POI 和天气查询均先于生成，并记录天气覆盖率和降级原因。
2. 对照 `legacy` 检查请求/响应字段、日期、预算、错误码和 SQLite 行程/会话版本兼容性；缺失天气按契约保留 `unknown`/`null`，不能把 P2 的历史覆盖数字当作 P3 证据。
3. 将 Open-Meteo 实际覆盖和 7 日查询结果写入新的 P3-02 验收记录；超出供应商预测期或缺失的日期仍为 `unknown`。

当前真实适配器验证：2026-10-13 查询杭州 10 月 13 至 19 日，返回连续 7 日，来源均为 `Open-Meteo` 且全部带适配器获取时间。真实图链路结果见下节。

### 真实 LangGraph 联调记录（2026-10-13）

使用本地环境配置执行杭州 3 日请求（当天至未来第 2 天）；不记录密钥、模型响应或供应商原始响应，只保留节点和天气契约结果：

- `query_weather_7d` 在 `generate_base_itinerary` 之前成功完成，`weather_context` 覆盖 3 个请求日期，天气状态为 `succeeded`；
- `generate_base_itinerary`、`apply_authoritative_weather`、地图路线/图片补全均完成；最终 3 个 `DayPlan.weather` 均为 `available`，来源均为 `Open-Meteo`，且保留适配器获取时间；
- `critic_review` 成功通过，说明生成前证据与生成后权威回填按日期一致；
- 本地知识库节点记录 `not_configured` 降级，这是环境能力缺失，不影响天气证据和权威回填；POI 候选节点成功。

脱敏指标记录：天气覆盖率 `3/3`；POI 核实率 `1.0`；路线核实率 `1.0`；天气、POI、汇聚等生成前节点累计约 `19,952 ms`；基础生成约 `78,813 ms`；端到端约 `161,223 ms`；MoMA usage 为 `prompt_tokens=4,665`、`completion_tokens=4,740`、`total_tokens=9,405`。成功联调使用一次性 `300 s` MoMA 单次超时上限；同一环境使用默认 `180 s` 上限的另一次尝试记录为脱敏 `MOMA_TIMEOUT`，没有进入错误响应或天气事实。成功链路唯一降级原因为本地知识库 `not_configured`。

兼容性核对：`AGENT_RUNTIME=legacy` 仍构造原 `TripOrchestrator`，`langgraph` 才启用状态图；两条路径共用 `TripRequest`、`Itinerary`、天气字段、错误码和 SQLite 版本边界。legacy 的天气补全优先调用 `forecast_window`，旧式天气服务回退接口也已放宽到 7 天；现有 API、存储和 P2 历史 fixture 未改写。

因此 P3-02 的天气适配器、生成前证据、权威回填、来源标注和真实图链路均已完成验收。
