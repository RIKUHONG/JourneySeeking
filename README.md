# 觅旅（MiliTravel）

觅旅是旅行规划业务后端。新增业务代码统一以根目录 `app/`、`tests/` 为开发基线；当前仓库同时保留已经验证过的 `backend/` FastAPI → `MomaClient` → MoMA → FastAPI 基础链路，迁移完成前作为兼容参考。

## 当前阶段

- 已有：FastAPI 与 MoMA 客户端链路验证代码（`backend/`）。
- 正在进行：`TripRequest`、`Itinerary`、`POST /api/trip/generate` 以及行程 JSON 校验。
- 计划中：高德地图、天气服务、多轮修改和 Agent 编排。

## 本地运行

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

具体协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)，成员职责见 [docs/team-roles.md](docs/team-roles.md)，目标架构见 [docs/architecture.md](docs/architecture.md)，开发指南见 [docs/development.md](docs/development.md)，接口约定见 [docs/api-contract.md](docs/api-contract.md)。

## 参考项目

本地 `repo_inspect_20260923/` 是参考项目资料，不属于本仓库，已加入 `.gitignore`，不会被提交或推送。
