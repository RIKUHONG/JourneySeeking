# 觅旅开发指南

## 本地初始化

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd ..
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

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

## 成员开发位置

- 成员 A：`backend/app/api/`、`backend/app/models/`、`backend/app/services/trip_service.py`、`backend/tests/api/`；
- 成员 B：`backend/app/services/itinerary_generator.py`、`backend/app/services/prompt_builder.py`、`backend/app/integrations/moma_client.py`、`backend/tests/moma/`；
- 成员 C：`backend/app/integrations/amap_client.py`、`backend/app/integrations/weather_client.py`、`backend/app/config/settings.py`、`backend/tests/integrations/`。

修改接口时先更新 `docs/api-contract.md`，再更新模型、实现和测试。禁止把 API Key 写入代码、测试 fixture 或提交记录。

## 地图与天气配置

`MapService`、`WeatherService` 及其数据类型定义在 `backend/app/integrations/contracts.py`，统一错误定义在 `backend/app/integrations/errors.py`。地图和天气适配器分别调用 `Settings.validate_map()`、`Settings.validate_weather()` 校验配置；应用启动不要求这两项密钥。

地图读取 `AMAP_API_KEY`、`AMAP_BASE_URL`、`AMAP_TIMEOUT_SECONDS`、`AMAP_MAX_RETRIES`。天气读取 `WEATHER_API_KEY`、`WEATHER_BASE_URL`、`WEATHER_TIMEOUT_SECONDS`、`WEATHER_MAX_RETRIES`。两项服务默认使用高德 Web 服务 API 根地址；启用时可将同一高德 Key 分别填入 `AMAP_API_KEY` 和 `WEATHER_API_KEY`。天气客户端先通过地理编码获取城市 adcode，再查询预报。默认单次请求超时为 10 秒，最大额外重试次数为 2；网络错误、超时、HTTP 429 和 5xx 会重试，认证错误和高德业务错误不会重试。

外部服务错误使用 `MapServiceError` 或 `WeatherServiceError`，`reason` 标识配置、超时、网络、供应商或响应内容问题。对外错误码分别为 `MAP_SERVICE_ERROR`、`WEATHER_SERVICE_ERROR`，不包含供应商原始响应或密钥。

真实适配器为 `AmapClient` 和 `WeatherClient`，分别实现 POI 搜索与驾车/步行路线、高德天气预报。天气预报支持 1 至 4 天；超过高德 Web 服务预报范围的日期不能作为实时天气返回。离线测试可注入 `MockMapService(places=..., routes=...)` 和 `MockWeatherService(forecasts=...)`；构造 mock 时传入 `FailureReason` 可模拟超时、网络或供应商失败。mock 不读取密钥，也不创建 HTTP 客户端。
