# P2-10 端到端与观测验收（历史记录）

本文档记录 P2 的验收结果，不是 P3 的通过证据。P2 的真实记录中天气仍属于基础生成后的补全；P3 必须按照 [P3 Agent 化规划](p3-plan.md) 增加生成前 POI/天气节点、最多 7 天窗口和 LangGraph/legacy 对照验收。

## 2026-10-12 验收记录

本次在 `feature/p2-e2e-observability` 工作区执行了离线、浏览器和真实服务检查。

| 检查项 | 结果 | 证据/备注 |
| --- | --- | --- |
| 后端离线测试 | 通过 | `MOMA_MAX_TOKENS=8192 python -m pytest -q`，228 passed |
| 前端构建 | 通过 | `npm run build` |
| 桌面结果页 | 通过 | Chrome DevTools，1440x900；无横向溢出，3 个每日面板，5 张图片资源加载成功 |
| 手机结果页 | 通过 | Chrome DevTools，390x844；文档宽度 390，无横向溢出；地点图片区可见，第二日面板可展开 |
| 空表单错误提示 | 通过 | 3 个字段错误和提示消息均出现 |
| 真实生成 | 未通过 | 杭州三日行程，耗时 505.31 秒，在 `generation` 阶段以 `MomaServiceError` 结束 |
| 真实智能调整 | 未执行 | 真实生成失败，未获得可编辑的行程版本 |
| 真实 token 基线 | 未获得 | 生成没有返回 MoMA usage；编辑未执行 |
| 真实质量基线 | 未获得 | 未得到真实生成结果，不能记录 POI/路线核实率 |

### 2026-10-12 重试配置调整后的真实服务验收

在用户将 `MOMA_MAX_RETRIES=0` 后重新执行同一套真实流程。此次生成和编辑均成功，数据库仍使用临时 SQLite，未修改本地行程数据。

| 指标 | 实测结果 |
| --- | --- |
| 生成耗时 | 167.30 秒 |
| 智能调整耗时 | 130.72 秒 |
| 生成 Prompt tokens | 4,499 |
| 生成 completion tokens | 8,519 |
| 生成 total tokens | 13,018 |
| 调整 Prompt tokens | 4,505 |
| 调整 completion tokens | 5,917 |
| 调整 total tokens | 10,422 |
| POI 核实率 | 12 / 12 = 100% |
| 路线核实率 | 9 / 9 = 100% |
| 可用天气天数 | 2 / 3（P2 后置天气历史记录） |
| 有图片的景点 | 10 个 |
| 编辑版本 | 版本 1 -> 版本 2 |
| 非目标日期 | 保持不变 |
| 历史版本 | 保持不变 |
| Markdown 导出 | 3,912 bytes，成功 |
| PDF 导出 | 118,262 bytes，成功 |

本次真实服务验收状态为 **通过**。上一轮 `MOMA_MAX_RETRIES=1` 的 505.31 秒失败记录仍保留，说明外部服务存在偶发慢或失败；本次关闭重试后，单次请求在 240 秒超时预算内成功完成。生成耗时主要集中在 `itinerary_generation`（154.78 秒），地图、天气和图片补全分别约 5.02、1.13、5.92 秒。

浏览器截图保存在本机验收输出目录：`p2-10-desktop.png`、`p2-10-mobile.png`、`p2-10-mobile-places.png`。样例 fixture 不含 `image_url`，因此截图中的地点图片是前端默认图库资源；这次检查只验证布局和加载，不把它计作真实 POI 图片覆盖率。

全仓 `ruff check .` 当前仍有 4 个既有问题，`ruff format --check .` 当前仍有 5 个既有未格式化文件；本次新增验收脚本自身通过 Ruff 检查。真实生成失败说明外部服务验收门槛尚未满足，P2-10 维持“验收中”。

## 离线验收

以下测试不需要外部密钥，所有供应商均使用替身，数据库使用临时 SQLite：

```powershell
python -m pytest backend/tests/e2e -q
```

`test_generate_save_two_edits_history_and_exports` 串联：

1. 生成三日行程并验证 `X-Request-ID`。
2. 创建行程和版本 1。
3. 创建会话，执行两轮不同日期的局部编辑，得到版本 2、3。
4. 读取当前版本和版本 1，确认历史版本不可变。
5. 导出版本 3 的 Markdown 和 PDF，检查内容和媒体类型。
6. 删除会话和行程，确认当前版本及历史版本均返回 404。

同一套测试还验证编排器的实际调用路径、请求完成日志和请求 ID。`test_generation_failure_does_not_create_trip` 注入 MoMA 超时，确认返回稳定错误且不会产生行程记录。

## 运行时观测

`POST /api/trip/generate` 通过 `TripOrchestrator` 执行有限步骤。每个请求返回或回显 `X-Request-ID`，错误响应也包含 `request_id`。应用日志记录以下脱敏字段：

- `request_id`、HTTP 方法、路径和状态码
- 请求总耗时 `duration_ms`
- 编排步骤名称、状态、来源、步骤耗时和失败类别
- POI/路线核实率（地图补全可用时）
- MoMA 返回的 `token_usage`（供应商未返回时为空）

日志不记录完整 Prompt、API Key、供应商原始响应或内部异常堆栈。编排器的知识库、地图、天气和图片属于可选增强；失败时记录 `degraded` 并保留可用的基础行程。生成和 Critic 失败不会返回未校验行程。

## 故障注入矩阵

| 故障 | 预期行为 | 当前覆盖 |
| --- | --- | --- |
| MoMA 超时 | 504 `MOMA_TIMEOUT`，不创建行程 | E2E + 生成接口测试 |
| 知识库不可用 | 检索步骤降级，继续基础生成 | 编排测试 |
| 地图不可用 | 地图状态降级，基础行程可用 | 地图/天气服务测试 |
| 天气不可用 | 保留基础行程，天气为空或未知 | 天气服务测试 |
| 编辑失败 | 原版本不覆盖 | 编辑服务测试 |
| 版本冲突 | 409，旧版本不覆盖新版本 | 存储和会话测试 |
| 导出行程不存在 | 404 | 导出接口测试 |

## 真实服务手工检查

真实联调只在本地进行，在 `backend/.env` 配置 `MOMA_API_KEY`、`AMAP_API_KEY` 和 `WEATHER_API_KEY` 后启动：

```powershell
uvicorn backend.app.main:app --reload
```

记录生成请求的 `X-Request-ID`、HTTP 状态、总耗时、步骤降级原因和 POI/路线核实率。不得把密钥、完整 Prompt 或供应商原始响应写入仓库、Issue 或 CI。真实联调不是默认 CI 门槛。

## 部署与回滚检查

- 部署前运行 `python -m pytest -q` 和 `npm run build`。
- SQLite 文件通过 `TRIP_DATABASE_PATH` 指定；升级前备份该文件。
- 回滚应用代码时保留数据库文件，确认旧版本仍能读取当前契约字段。
- 发生外部服务故障时，先关闭对应增强配置或回退到上一应用版本；不要删除行程数据库。

## P3 迁移验收补充

P3 不复用本文件中的 P2 真实天气覆盖数字作为新链路证据。新验收必须单独记录：

- `search_poi_candidates`、`query_weather_7d` 在 `generate_base_itinerary` 之前完成或明确降级；
- 3、4、7 天请求的天气覆盖率、部分覆盖和 `unknown` 日期；
- 天气证据是否进入 Planner Prompt，以及供应商天气是否在生成后权威回填；
- LangGraph 与 `AGENT_RUNTIME=legacy` 的日期、预算、POI、天气和降级结果对照；
- 图版本、Prompt 版本、工具调用耗时和脱敏 trace。
