# 觅旅三人团队分工与协作任务

本文档是当前阶段的执行清单。每位成员按指定分支开发，通过 Issue 跟踪工作，通过 Pull Request 合并；禁止直接向 main 推送。

## 共同准备

所有成员先执行：git checkout main；git pull --ff-only origin main。
所有成员先阅读 CONTRIBUTING.md 和 docs/api-contract.md。每个 Issue 完成后运行相关测试，并在 PR 中填写验证命令和结果。

## 成员 A：API、模型与行程校验

分支：feature/api-contract
创建：git checkout -b feature/api-contract
开发基线：`backend/app/api/`、`backend/app/models/`、`backend/app/services/trip_service.py`、`backend/tests/api/`
Issue 标题：[成员A][P0] 实现 TripRequest、Itinerary 和行程生成 API
Issue 范围：定义 TripRequest、Activity、DayPlan、Itinerary；实现 POST /api/trip/generate 和 TripService；校验 MoMA JSON；统一错误响应；补充 API/异常测试；按需更新接口契约。不包括高德、天气、Agent 和前端。
验收标准：
- 合法请求返回合法 Itinerary；
- 缺少目的地、日期非法或日期倒置返回明确 4xx；
- MoMA 缺字段、类型错误或非法 JSON 返回统一错误；
- 正常、参数错误、超时、非法响应均有测试；
- 路由层不直接拼接 Prompt 或调用外部服务。
提交示例：feat: add trip and itinerary schemas；feat: add trip generation endpoint；test: cover itinerary validation errors。
PR 标题：feat(api): add trip generation contract and validation。PR 必须关联 Issue，说明接口示例、错误码变化、测试命令和环境变量影响；B 检查 MoMA，C 检查配置耦合。

## 成员 B：MoMA 生成、解析与 mock

分支：feature/moma-itinerary-generator
创建：git checkout -b feature/moma-itinerary-generator
开发基线：`backend/app/services/itinerary_generator.py`、`backend/app/services/prompt_builder.py`、`backend/app/integrations/moma_client.py`、`backend/tests/moma/`
Issue 标题：[成员B][P0] 实现 MoMA 结构化行程生成与响应解析
Issue 范围：实现 PromptBuilder、ItineraryGenerator；约束 MoMA 输出 JSON；处理 Markdown 代码块、空响应、非法 JSON、字段缺失和类型错误；实现受控重试/一次修复；提供 mock 客户端和正常/非法/边界 fixtures。不包括 HTTP 路由、地图、天气和 Agent。
验收标准：
- mock 与真实 MomaClient 接口一致；
- 处理正常 JSON、json 代码块和非法 JSON；
- 超时、空响应和校验失败转换为统一错误；
- Prompt 包含目的地、日期、人数和偏好；
- MoMA 客户端不包含 FastAPI 路由逻辑；
- 解析分支均有不依赖 API Key 的离线测试。
提交示例：feat: add structured itinerary prompt builder；feat: parse and validate MoMA itinerary output；test: add malformed MoMA response fixtures。
PR 标题：feat(moma): generate and parse structured itineraries。PR 必须关联 Issue 并附成功/失败样例；A 确认字段一致，C 检查超时、配置和密钥。

## 成员 C：高德、天气与工程基础设施

分支：feature/external-service-foundation
创建：git checkout -b feature/external-service-foundation
开发基线：`backend/app/integrations/amap_client.py`、`backend/app/integrations/weather_client.py`、`backend/app/config/settings.py`、`backend/tests/integrations/`
Issue 标题：[成员C][P1] 建立地图、天气服务抽象和配置基础设施
Issue 范围：定义 MapService/WeatherService；创建 amap_client.py 和 weather_client.py；加入超时、错误转换、重试、离线 mock、.env.example/settings、外部服务测试和配置文档。不包括修改 MoMA Prompt 和完整 Agent。
验收标准：
- API Key 不进入 Git；
- 地图和天气客户端有明确超时；
- 网络失败、供应商错误和空响应有统一错误模型；
- mock 无网络也能测试；
- 外部服务不可用时核心服务仍能启动；
- .env.example 与代码读取变量一致。
提交示例：feat: add map and weather service interfaces；feat: add external service configuration and timeouts；test: add offline map and weather mocks。
PR 标题：feat(integrations): add map weather abstractions and configuration。PR 必须关联 Issue，列出新增环境变量、超时策略和 mock；A 检查核心 API，B 检查 Prompt 解耦。

## 联调 Issue 与 PR

个人 PR 合并后，由 A 创建 Issue：[全员][P0] 联调 FastAPI → MoMA → Itinerary 完整链路。
顺序：A 合并模型和 API 契约 → B 接入 MoMA 生成器 → C 合并 mock/配置/错误基础设施 → 全员运行端到端 mock 测试 → 通过后再接入真实 MoMA、高德和天气。
联调 PR 标题：feat(trip): integrate structured itinerary generation pipeline。
联调验收：POST /api/trip/generate 可用 mock MoMA 返回合法行程；请求、模型、Prompt、解析和校验链路完整；超时、非法响应和外部服务失败可控；测试不要求真实 API Key；OpenAPI 与 docs/api-contract.md 一致。

## 后续 Issue 顺序

[P1] 接入高德地点搜索和路线规划
[P1] 接入天气预报并增强行程建议
[P2] 增加行程局部修改 API
[P2] 增加多轮对话状态管理
[P2] 引入 Agent 编排和工具调用

P0 链路稳定前，不创建改变核心数据契约的 Agent 分支。

## 分工总览

| 成员 | 分支 | 主要 Issue | 主要 PR |
|---|---|---|---|
| A | feature/api-contract | 模型、API、校验 | feat(api): add trip generation contract and validation |
| B | feature/moma-itinerary-generator | Prompt、解析、重试、mock | feat(moma): generate and parse structured itineraries |
| C | feature/external-service-foundation | 地图、天气、配置、降级 | feat(integrations): add map weather abstractions and configuration |

## 共同规则

- 分支从最新 main 创建，完成后通过 PR 合并；
- 每个 PR 至少一名其他成员 review；
- API 字段先更新契约和测试，再修改实现；
- PR 合并前解决所有 review 意见；
- 不提交 .env、API Key、真实用户数据或参考项目目录；
- PR 合并后删除远端功能分支。
