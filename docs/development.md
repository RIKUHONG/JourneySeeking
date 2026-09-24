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
