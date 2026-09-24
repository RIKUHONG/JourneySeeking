# JourneySeeking

JourneySeeking 是智旅云图的业务后端。当前仓库包含已经验证过的 FastAPI → `MomaClient` → MoMA → FastAPI 基础链路，并以此为基础逐步接入结构化行程生成、地图、天气和后续 Agent 编排。

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

具体协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)，成员职责见 [docs/team-roles.md](docs/team-roles.md)，接口约定见 [docs/api-contract.md](docs/api-contract.md)。

## 参考项目

本地 `repo_inspect_20260923/` 是参考项目资料，不属于本仓库，已加入 `.gitignore`，不会被提交或推送。
