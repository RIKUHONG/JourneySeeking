# 觅旅开发指南

## 本地初始化

```powershell
python -m pip install -e ".[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

以上命令均从仓库根目录执行。若使用虚拟环境，先创建并激活环境，再安装依赖。本地 `.env` 只用于开发，不提交到 Git。

## 启动服务

```powershell
uvicorn backend.app.main:app --reload
```

## 测试与质量检查

```powershell
pytest
ruff check .
ruff format --check .
```

每个新模块都应在 `tests/` 添加对应测试。测试默认使用 mock，不调用真实 MoMA、高德或天气 API。

当前仓库的全量 Ruff 检查仍可能报告未在本次任务中修改的 P0 文件问题。每个 PR 至少应保证自身改动文件通过 Ruff 检查，并在 PR 中列明全量检查结果；不要顺带大规模格式化其他成员的代码。

## 成员开发位置

- 成员 A：`backend/app/api/`、`backend/app/models/`、`backend/app/services/trip_service.py`、`backend/tests/api/`；
- 成员 B：`backend/app/services/itinerary_generator.py`、`backend/app/services/prompt_builder.py`、`backend/app/integrations/moma_client.py`、`backend/tests/moma/`；
- 成员 C（P1 业务接入）：在 `backend/app/services/` 增加地点/路线补全与天气建议，复用 `backend/app/integrations/` 的现有客户端和 mock；测试放在 `backend/tests/` 对应位置。若修改 `backend/app/models/` 或 `backend/app/main.py`，先与 A 审核 API 契约。

修改接口时先更新 `docs/api-contract.md`，再更新模型、实现和测试。禁止把 API Key 写入代码、测试 fixture 或提交记录。

## 地图与天气配置

`MapService`、`WeatherService` 及其数据类型定义在 `backend/app/integrations/contracts.py`，统一错误定义在 `backend/app/integrations/errors.py`。地图和天气适配器分别调用 `Settings.validate_map()`、`Settings.validate_weather()` 校验配置；应用启动不要求这两项密钥。

地图读取 `AMAP_API_KEY`、`AMAP_BASE_URL`、`AMAP_TIMEOUT_SECONDS`、`AMAP_MAX_RETRIES`。天气读取 `WEATHER_API_KEY`、`WEATHER_BASE_URL`、`WEATHER_TIMEOUT_SECONDS`、`WEATHER_MAX_RETRIES`。两项服务默认使用高德 Web 服务 API 根地址；启用时可将同一高德 Key 分别填入 `AMAP_API_KEY` 和 `WEATHER_API_KEY`。天气客户端先通过地理编码获取城市 adcode，再查询预报。默认单次请求超时为 10 秒，最大额外重试次数为 2；网络错误、超时、HTTP 429 和 5xx 会重试，认证错误和高德业务错误不会重试。

外部服务错误使用 `MapServiceError` 或 `WeatherServiceError`，`reason` 标识配置、超时、网络、供应商或响应内容问题。对外错误码分别为 `MAP_SERVICE_ERROR`、`WEATHER_SERVICE_ERROR`，不包含供应商原始响应或密钥。

真实适配器为 `AmapClient` 和 `WeatherClient`，分别实现 POI 搜索与驾车/步行路线、高德天气预报。天气预报支持 1 至 4 天；超过高德 Web 服务预报范围的日期不能作为实时天气返回。离线测试可注入 `MockMapService(places=..., routes=...)` 和 `MockWeatherService(forecasts=...)`；构造 mock 时传入 `FailureReason` 可模拟超时、网络或供应商失败。mock 不读取密钥，也不创建 HTTP 客户端。

## P1 接入顺序与本地验证

1. 从最新 `main` 为高德地点/路线 Issue 创建独立分支。先更新 `docs/api-contract.md` 并增加离线测试，再把 `MapService` 注入行程业务层；合并该 PR 后再启动天气 Issue。
2. 为天气 Issue 从最新 `main` 创建新分支，按行程日期使用 `WeatherService`。缺失或超出预报范围的天气保持未知，不填充推测值。
3. 两项任务都要用 mock 测试正常、部分结果、超时和供应商失败；校验无地图/天气 Key 时 `/health` 与 P0 核心链路仍可运行。真实高德 Key 的连通性测试单独执行，不进入默认测试套件。

地图与天气补全属于 `services` 层的可选能力。路由不直接创建供应商客户端；业务层通过接口接受真实服务或 mock。现阶段 `POST /api/trip/generate` 尚未调用这些服务，不能把客户端已有能力描述为已上线的行程功能。
