# 三人团队分工

## 成员 A：API、模型与校验负责人

### 职责

- 定义 `TripRequest`、`Itinerary` 及其子模型；
- 实现 `POST /api/trip/generate`；
- 统一处理请求校验和错误响应；
- 校验 MoMA 返回的行程 JSON；
- 编写 API、模型和异常场景测试；
- 维护 `docs/api-contract.md` 中的接口变化。

### 交付物

- `backend/app/api/`；
- `backend/app/models/`；
- `backend/app/services/trip_service.py`；
- API 测试；
- OpenAPI 示例和接口文档。

### 验收标准

- 合法请求返回合法 `Itinerary`；
- 非法请求返回明确的 `4xx`；
- MoMA 非法响应不会直接泄露内部异常；
- 正常、参数错误、超时、非法 JSON 均有测试。

## 成员 B：MoMA 生成与解析负责人

### 职责

- 将 `TripRequest` 转换为 MoMA Prompt；
- 约束 MoMA 输出结构化 JSON；
- 实现解析、代码块剥离、一次修复/重试和校验衔接；
- 保持 `MomaClient`、Prompt 构造和业务生成逻辑解耦；
- 提供 mock MoMA 和固定回归样例。

### 交付物

- `backend/app/moma_client.py` 的适配层维护；
- `prompt_builder` / `itinerary_generator`；
- `backend/tests/fixtures/` 中的响应样例；
- MoMA 解析和失败场景测试。

### 验收标准

- mock 和真实客户端具有相同调用接口；
- 能处理正常 JSON、Markdown 代码块和非法 JSON；
- 字段缺失、类型错误和超时都能转换为统一错误；
- 不把路由逻辑写进 MoMA 客户端。

## 成员 C：外部服务与工程基础设施负责人

### 职责

- 设计高德地图和天气服务抽象；
- 实现配置加载、超时、重试和降级；
- 提供地图/天气 mock，便于离线测试；
- 维护 `.env.example`、本地运行说明和 CI 基础配置；
- 为后续把地点、路线和天气追加到行程预留模型。

### 交付物

- `backend/app/integrations/`；
- `backend/app/config/`；
- 地图和天气接口测试；
- `.env.example`、部署和开发文档。

### 验收标准

- API Key 不进入 Git；
- 外部服务有明确超时和错误模型；
- mock 不依赖网络；
- 外部服务失败时可以降级，不影响核心服务启动。

## 共同约定

- 三人共同维护 `TripRequest`、`Itinerary` 和错误码契约；
- 成员 A 负责最终 API 契约合并，成员 B 负责 MoMA 输出契约，成员 C 负责外部服务契约；
- 新字段先更新文档和测试，再更新实现；
- 每个功能分支通过 Pull Request 合并，至少一人 review；
- 第一阶段优先完成结构化行程生成，不提前引入复杂 Agent 编排。

## 建议里程碑

1. M1：模型、错误码、接口契约和 mock 完成；
2. M2：FastAPI → MoMA → `Itinerary` 校验链路联调通过；
3. M3：高德和天气服务接入；
4. M4：多轮修改和 Agent 编排。
