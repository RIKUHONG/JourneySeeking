# 觅旅开发指南

## 本地初始化与运行

从仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uvicorn backend.app.main:app --reload
```

`/health` 检查进程，`/docs` 展示当前 OpenAPI。真实 MoMA 调用需要 `MOMA_API_KEY`；地图和天气客户端分别使用 `AMAP_API_KEY`、`WEATHER_API_KEY`，都不是启动硬依赖。其他设置以 `backend/.env.example` 和 `backend/app/config/settings.py` 为准。

## 验证

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

测试默认使用 mock，不访问 MoMA 或高德。2026-09-29 `main` 离线测试为 136 passed；真实服务联调单独记录。历史 Ruff 问题不得借 P2 功能 PR 大范围格式化；每个 PR 至少保证改动文件通过并记录全量检查结果。

## P2 协作

P2 工作面、依赖和验收见 [P2 Issue 草案](p2-issues.md)，负责人待定。每个 Issue 从合并后的最新 `main` 建独立分支，关联 PR，至少一名非作者评审。修改共享字段时先更新 [API 契约](api-contract.md) 与契约测试，再修改模型、服务、前端。存储迁移、环境变量、降级和回滚行为须写在 PR 中。

`MapService`、`WeatherService` 的接口及错误类型在 `backend/app/integrations/`；`MapEnrichmentService` 和 `WeatherEnrichmentService` 已进入生成链路。地图使用进程内缓存，失效时按未命中处理；天气最多查询四天，缺失日期为未知。P2 不应重复建立这些基础设施。`/api/chat` 是普通消息转发，不保存行程状态。

新后端模块添加对应离线测试。前端从 P2-01 契约 mock 开发，最终按 OpenAPI 接口集成。不得提交密钥、真实用户数据、本地数据库或 `repo_inspect_20260923/`。
