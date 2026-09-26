# 觅旅目标架构

## 目录基线

后端业务代码统一放在 `backend/app/`，测试统一放在 `backend/tests/`。以下列出当前已存在的主要文件；P1 业务接入服务尚未创建。

```text
Journey_Seeking/
├── backend/
│   ├── app/
│   │   ├── main.py                    # 当前 HTTP 路由与依赖注入
│   │   ├── models/schemas.py          # TripRequest、Itinerary 等 P0 契约
│   │   ├── services/                  # 行程生成与校验；P1 补全逻辑将放在此处
│   │   ├── integrations/              # MoMA、高德、天气客户端、接口及 mock
│   │   └── config/settings.py
│   ├── tests/                          # api/、moma/、integrations/
│   └── .env.example
├── docs/
├── pyproject.toml
└── docker-compose.yml
```

## 分层规则

- `backend/app/main.py`：当前 FastAPI 路由、错误映射和依赖注入；业务规则放在 service 层。后续如拆分 `api/`，仍保持相同边界。
- `backend/app/models/`：Pydantic 数据模型；`TripRequest` 与 `Itinerary` 是第一版核心契约。
- `backend/app/services/`：旅行生成、Prompt 构造、校验和编排。
- `backend/app/integrations/`：MoMA、高德、天气等外部服务适配器；`contracts.py` 与 `errors.py` 定义地图/天气边界，mock 与真实客户端实现同一接口。
- `backend/app/config/`：环境变量和运行配置。
- `backend/tests/`：与 `backend/app/` 一一对应的单元和集成测试。

依赖方向固定为：`HTTP 路由 → services → integrations`。`integrations` 不得反向依赖路由；模型层不发起网络请求。P1 地点/路线和天气补全从行程业务层调用可注入的服务接口，不在供应商客户端内修改 `Itinerary` 或拼接 MoMA Prompt。

## P1 数据流与降级

当前链路是 `TripRequest → MoMA 生成 → TripService 校验 → Itinerary`。P1 接入后，地点、路线和天气只处理已经通过 P0 校验的行程，按需补充可核实的信息；现有必填字段与校验仍然有效。

- 地点搜索返回零结果与供应商失败是两种不同状态；没有可靠 POI 时保留原活动，不写入伪造的 ID 或坐标。
- 路线要求已知起终点坐标，距离和耗时只能来自对应交通方式的高德结果；缺失路线时保留基础行程。
- 天气只对应预报覆盖的日期。当前客户端最多提供 4 天预报，3 至 7 天行程中其余日期保持未知。
- 地图或天气不可用时，核心应用仍可启动，基础行程仍可返回；若对外展示补全状态或告警，字段需先进入 API 契约并经评审。
