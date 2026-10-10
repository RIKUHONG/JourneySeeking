# 觅旅（MiliTravel）

觅旅是旅行规划项目。当前仓库是 Python 3.11+ 后端，业务代码在 `backend/app/`，测试在 `backend/tests/`；前端尚未建立。长期目标见 [软件开发文档](觅旅-MoMA软件开发文档.md)，当前执行基线见 [路线图](docs/roadmap.md)。

## 项目状态（2026-09-29）

| 阶段 | 状态 | 当前代码 |
| --- | --- | --- |
| P0 | 已完成 | `TripRequest` / `Itinerary`、`POST /api/trip/generate`、MoMA 生成与校验 |
| P1 | 已进入 `main` | 候选 POI ID 校验、高德地点/路线补全、进程内地图缓存、逐日天气与轻量建议 |
| 生成链路修复 | 已进入本地 `main` | `6f76009`，包含生成补全修复和杭州真实生成样例 |
| P2 | 已分工、待开发 | [差距对比与 Issue 清单](docs/p2-issues.md)：A/B/C 的分支、工作范围、内容与验收 |

`/api/chat` 已有原始 MoMA 对话转发，但不是行程会话或多轮编辑接口。Redis adapter 和天气自动调度尚未实现，也不是 P2 核心完成门槛。

## 本地运行

在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uvicorn backend.app.main:app --reload
```

访问 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:8000/docs`。真实 MoMA 生成需要在本地 `backend/.env` 设置 `MOMA_API_KEY`；真实地图/天气调用还需对应高德密钥。离线测试与应用启动不要求地图/天气密钥。不要提交 `.env` 或真实密钥。

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

2026-09-29 的本地 `main`（`6f76009`）上离线测试为 142 passed。杭州真实生成样例保存在 `docs/fixtures/trip-generate-hangzhou-20260929.json`；真实外部服务联调不属于默认测试套件。仓库级 Ruff 仍可能报告历史问题；新 PR 至少应保证改动文件通过，并记录全量结果。

接口见 [API 契约](docs/api-contract.md)，代码边界见 [架构](docs/architecture.md)，开发流程见 [开发指南](docs/development.md)，团队工作面见 [协作分工](docs/team-roles.md)。

## 参考项目

根目录下的本地 `helloagents-trip-planner/` 用来核对能力差距，不属于本项目的交付代码，也不得提交到 Git。两个项目的 API 路径、行程数据模型和存储结构不同；P2 以本仓库契约为准。
