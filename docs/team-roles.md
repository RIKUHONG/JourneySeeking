# 觅旅三人团队分工与协作任务

本文档是当前阶段的执行清单。P0 的 A/B 任务和成员 C 的 P1 外部服务基础设施已合并；接下来由成员 C 负责两个独立的 P1 业务接入 Issue。每个 Issue 使用从最新 `main` 创建的独立分支，通过 Pull Request 合并；禁止直接向 `main` 推送。

## 共同准备

所有成员先执行：`git checkout main`；`git pull --ff-only origin main`。
所有成员先阅读 `CONTRIBUTING.md` 和 `docs/api-contract.md`。每个 Issue 完成后运行相关测试，并在 PR 中填写验证命令和结果。以下“已完成”小节保留原 Issue 记录，分支创建命令无需重复执行。

## 已完成：成员 A 的 P0 API、模型与行程校验

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

## 已完成：成员 B 的 P0 MoMA 生成、解析与 mock

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

## 已完成：成员 C 的 P1 外部服务基础设施

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

## 待开发：成员 C 的 P1 高德地点与路线接入

建议分支：`feature/amap-trip-enrichment`；Issue 标题：`[成员C][P1] 接入高德地点搜索和路线规划`。

工作范围：在已合并的 `MapService` / `AmapClient` 基础上，为行程活动查找真实 POI，并在有可靠坐标的活动之间规划驾车或步行路线；把匹配结果、路线估算和数据来源传给业务层。优先在 `backend/app/services/` 增加可注入的补全逻辑，并在 `backend/tests/` 添加服务与 API 测试。参考项目的 POI 搜索、路线调用可作设计参考，不能直接复制其数据模型或缓存依赖。

执行顺序：先与 A 确认需要暴露的可选字段或独立接口，并更新 `docs/api-contract.md` 和测试；再实现地点匹配、路线补全及 API 接入。不能以名称相似为由把错误 POI 标记为已核实，也不能用模型臆造 POI ID、坐标或路线时长。

验收标准：

- 已匹配的活动可追溯到高德 POI ID、地址和坐标；未匹配项明确保持未核实，不填假数据；
- 只有可靠的起终点坐标才规划路线，距离与耗时来自高德响应，并注明交通方式；
- 零搜索结果、歧义匹配、无坐标、路线为空、超时和供应商失败均有确定处理；
- 地图失败时仍能返回通过 P0 校验的基础行程，并清楚区分未补全与已核实数据；
- 现有请求字段及 `Itinerary` 必填字段语义不变，新增响应内容经 A 评审且与 OpenAPI 一致；
- 使用离线 mock 覆盖正常、失败和部分补全场景；真实 Key 仅用于单独的连通性检查。

建议 PR 标题：`feat(trip): enrich itinerary with amap places and routes`。A review API 契约和行程校验，B review 生成器边界；PR 写明匹配规则、失败时的返回行为和验证结果。

## 待开发：成员 C 的 P1 天气预报与行程建议

建议分支：`feature/weather-trip-advice`；Issue 标题：`[成员C][P1] 接入天气预报并增强行程建议`。从高德接入 PR 合并后的最新 `main` 创建分支。

工作范围：通过已合并的 `WeatherService` / `WeatherClient` 获取目的地预报，把可用日期的天气与行程日期对应，并对雨天等影响户外活动的情况生成明确、可测试的建议。天气建议属于业务层，不由 HTTP 路由或天气客户端直接修改 MoMA Prompt；自动改变活动安排须另行评审。

执行顺序：先与 A 确认天气和建议的可选响应结构并更新 `docs/api-contract.md` 和测试；再实现日期匹配、建议规则及 API 接入。高德预报目前最多 4 天，而请求允许 3 至 7 天；超出预报范围的日期不得标成实时预报。

验收标准：

- 天气按日期与行程对应，并标明来源、获取时间或可用范围；
- 有天气依据的建议能区分正常天气、雨天和未知天气，不凭空承诺停业、降雨时段或替代景点；
- 对超过预报范围、无城市 adcode、空预报、超时和供应商失败有确定处理；
- 天气不可用时基础行程仍可返回，未知日期不显示伪造天气；
- 离线 mock 覆盖正常、雨天、部分日期、超时和失败场景，现有 P0 测试继续通过；
- 新增响应内容经 A 评审且与 OpenAPI 一致。

建议 PR 标题：`feat(trip): add weather-aware itinerary advice`。A review API 契约，B review MoMA 解耦；PR 写明预报范围、建议规则、降级行为和验证结果。

## P0 链路与 P1 衔接

当前 `POST /api/trip/generate` 已连接请求模型、MoMA 生成器、JSON 解析和 `Itinerary` 校验，并有离线测试。地图与天气尚未接入该链路。若仍需单独开展真实 MoMA 联调，由 A/B 负责按现有 API 契约验证；成员 C 的两个 P1 Issue 从已校验的基础行程开始补全，不重新定义 P0 生成流程。

## 后续 Issue 顺序

[P1][成员C] 接入高德地点搜索和路线规划（上文第一个待开发 Issue）
[P1][成员C] 接入天气预报并增强行程建议（上文第二个待开发 Issue）
[P2] 增加行程局部修改 API
[P2] 增加多轮对话状态管理
[P2] 引入 Agent 编排和工具调用

P1 两个 Issue 分别提交 PR；先完成地点和路线，再在最新 `main` 上接入天气。P2 不在当前两个 Issue 中。

## 分工总览

| 成员 | 当前状态 | 本阶段职责 | 协作方式 |
|---|---|---|---|
| A | 已完成 | P0 模型、API、校验 | P1 接口契约 review |
| B | 已完成 | P0 Prompt、解析、重试、mock | P1 MoMA 边界 review |
| C | 基础设施已完成；业务接入待开发 | P1 高德地点/路线、天气建议 | 两个独立 PR，见上文 |

## 共同规则

- 分支从最新 main 创建，完成后通过 PR 合并；
- 每个 PR 至少一名其他成员 review；
- API 字段先更新契约和测试，再修改实现；
- PR 合并前解决所有 review 意见；
- 不提交 .env、API Key、真实用户数据或参考项目目录；
- PR 合并后删除远端功能分支。
