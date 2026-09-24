# 觅旅目标架构

## 目录基线

从本阶段开始，新增后端业务代码统一放在 `backend/app/`，测试统一放在 `backend/tests/`。项目根目录预留给前端、文档和基础设施，不在根目录创建后端 `app/`。

```text
Journey_Seeking/
├── frontend/                 # 后续前端目录（当前可暂不创建）
├── backend/
│   ├── app/
│   ├── main.py
│   ├── api/trip.py
│   ├── models/trip.py
│   ├── models/itinerary.py
│   ├── schemas/
│   ├── services/trip_service.py
│   ├── services/itinerary_generator.py
│   ├── services/prompt_builder.py
│   ├── integrations/moma_client.py
│   ├── integrations/amap_client.py
│   ├── integrations/weather_client.py
│   └── config/settings.py
│   └── tests/
├── docs/
├── .env.example
├── pyproject.toml
└── docker-compose.yml
```

## 分层规则

- `backend/app/main.py`：创建 FastAPI 应用和生命周期，不放业务逻辑。
- `backend/app/api/`：HTTP 路由、状态码和依赖注入，不直接调用供应商 SDK。
- `backend/app/models/`：领域模型和 Pydantic 数据模型；`TripRequest` 与 `Itinerary` 是第一版核心契约。
- `backend/app/schemas/`：外部服务输入输出、错误响应和跨层 DTO。
- `backend/app/services/`：旅行生成、Prompt 构造、校验和编排。
- `backend/app/integrations/`：MoMA、高德、天气等外部服务适配器。
- `backend/app/config/`：环境变量和运行配置。
- `backend/tests/`：与 `backend/app/` 一一对应的单元和集成测试。

依赖方向固定为：`api → services → integrations`。`integrations` 不得反向依赖路由；模型层不发起网络请求。

## 迁移规则

现有 `backend/app/moma_client.py` 是已验证实现。成员 B 应将其能力迁移或封装到 `backend/app/integrations/moma_client.py`，并用测试证明行为一致，再删除旧代码。迁移期间不要同时修改两套实现的业务行为。
