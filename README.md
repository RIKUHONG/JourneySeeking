# 觅旅（MiliTravel）

觅旅是包含前后端的旅行规划项目。后端新增业务代码统一以 `backend/app/`、`backend/tests/` 为开发基线；根目录不放后端 `app/`，未来可在根目录增加前端目录。当前 `backend/` 包含已经验证过的 FastAPI → `MomaClient` → MoMA → FastAPI 基础链路。

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
