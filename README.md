# 觅旅（MiliTravel）

觅旅是旅行规划项目。当前仓库包含 Python 3.11+ 后端和 Vue 3/TypeScript 前端，业务代码在 `backend/app/`，测试在 `backend/tests/`。长期目标见 [软件开发文档](觅旅-MoMA软件开发文档.md)，当前执行基线见 [路线图](docs/roadmap.md)。P3 的状态图和实施边界见 [P3 Agent 化规划](docs/p3-plan.md)。

## 项目状态（2026-09-29）

| 阶段 | 状态 | 当前代码 |
| --- | --- | --- |
| P0 | 已完成 | `TripRequest` / `Itinerary`、`POST /api/trip/generate`、MoMA 生成与校验 |
| P1 | 已进入 `main` | 候选 POI ID 校验、高德地点/路线补全、进程内地图缓存、逐日天气与轻量建议 |
| 生成链路修复 | 已进入本地 `main` | `6f76009`，包含生成补全修复和杭州真实生成样例 |
| P2 | 核心功能已合入，作为 P3 迁移基线 | [差距对比与 Issue 清单](docs/p2-issues.md) |
| P3 | P3-01、P3-02 已实现 | LangGraph 状态图、生成前 POI/7 天天气、Prompt 工程、MCP 工具和评测驱动 RAG |

`/api/chat` 已有原始 MoMA 对话转发，但不是行程会话或多轮编辑接口。`AGENT_RUNTIME=langgraph` 在基础生成前查询最多 7 天的 Open-Meteo 预报，`legacy` 保留生成后查询路径；两条路径均以 Open-Meteo 为天气事实来源，高德仅提供城市坐标。天气驱动的已保存行程自动调整仍需用户确认，不属于基础生成图。

## 本地运行

在仓库根目录执行：

```powershell
python -m pip install -e ".[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
uvicorn backend.app.main:app --reload
```

访问 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:8000/docs`。真实 MoMA 生成需要在本地 `backend/.env` 设置 `MOMA_API_KEY`；真实地图与天气城市定位需要 `AMAP_API_KEY`，Open-Meteo 预报不需要天气密钥。离线测试与应用启动不要求密钥。不要提交 `.env` 或真实密钥。

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

当前离线后端测试和 P2-10 E2E 验收命令见 [P2-10 验收记录](docs/p2-10-e2e-observability.md)。杭州真实生成样例保存在 `docs/fixtures/trip-generate-hangzhou-20260929.json`；真实外部服务联调不属于默认测试套件。

接口见 [API 契约](docs/api-contract.md)，代码边界见 [架构](docs/architecture.md)，开发流程见 [开发指南](docs/development.md)，团队工作面见 [协作分工](docs/team-roles.md)。

完整手工验收步骤见 [手工测试流程](docs/manual-test-guide.md)，后端测试端口为 `8000`。

## 参考项目

根目录下的本地 `helloagents-trip-planner/` 用来核对能力差距，不属于本项目的交付代码，也不得提交到 Git。两个项目的 API 路径、行程数据模型和存储结构不同；P2 以本仓库契约为准。
