# 觅旅（MiliTravel）

觅旅是旅行规划项目。目前仓库以 Python 3.11+ 后端为主，业务代码位于 `backend/app/`，测试位于 `backend/tests/`；前端目录尚未建立。

## 项目状态

| 阶段 | 状态 | 已有能力或下一步 |
| --- | --- | --- |
| P0 | 已完成 | `TripRequest` / `Itinerary` 契约、`POST /api/trip/generate`、MoMA 生成与校验、离线测试 |
| P1 基础设施（成员 C） | 已完成 | 高德 POI/驾车及步行路线客户端、天气客户端、可替换接口、错误模型、配置与离线 mock |
| P1 业务接入（成员 C） | 待开发 | 用真实 POI 和路线补充行程；接入天气预报并增强行程建议 |
| P2 | 计划中 | 局部修改、多轮状态管理和 Agent 编排 |

地图和天气客户端目前尚未接入 `POST /api/trip/generate` 的业务流程；该接口现阶段仍返回 P0 的 `Itinerary`。P1 任务和验收条件见 [团队分工](docs/team-roles.md)。

## 本地运行

在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uvicorn backend.app.main:app --reload
```

访问 `http://127.0.0.1:8000/health` 检查启动状态；`http://127.0.0.1:8000/docs` 查看当前 OpenAPI。调用真实 MoMA 生成行程前，需要在本地 `backend/.env` 中填写 `MOMA_API_KEY`。地图、天气密钥在应用启动和离线测试时不是必需的；调用对应真实客户端时才需要配置。不要提交 `.env` 或真实密钥。

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

仓库级 Ruff 检查目前仍有部分 P0 文件的历史问题；新 PR 至少应保证改动文件通过检查，并在 PR 中记录全量检查结果。

开发流程见 [开发指南](docs/development.md)，外部接口见 [API 契约](docs/api-contract.md)，代码分层见 [架构](docs/architecture.md)，协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 参考项目

本地 `repo_inspect_20260923/` 用于参考高德和天气的后端设计，不属于本仓库，也不应提交。后续业务接入以本仓库的接口契约和测试为准。
