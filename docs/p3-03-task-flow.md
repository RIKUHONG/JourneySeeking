# P3-03 Prompt 版本与评测任务流程

状态：已完成代码与离线回归；真实模型成对 A/B 尚未验收，默认生成 Prompt 保持 `p3-02-compat`。范围与总验收门槛以 [P3 规划](p3-plan.md) 为准。本文细化生成、结构修复、Critic 修复和单日编辑的 Prompt 版本、输出 Schema、脱敏元数据与离线 A/B；不启动 P3-04 MCP、P3-05 RAG 排序或天气驱动的已保存行程重规划。

## 当前基线与风险

- P3-01/P3-02 已提供 LangGraph 前置 POI、RAG、7 天天气及权威回填；`AGENT_RUNTIME=legacy` 仍可回滚编排。P3-03 保持 HTTP、SQLite 版本、天气和 POI 事实边界不变。
- `PromptBuilder` 目前以字符串拼接生成行程 Prompt；`ItineraryGenerator` 内置一次 JSON 修复；图中的 `repair_structured_output` 和 `repair_with_critic_findings` 均通过再次调用 `generate_base` 生成草稿。需要先厘清内部修复与图修复的共享次数，不能让一次图节点隐含额外模型调用。
- P2 提交 `dec7425` 中的生成 Prompt 没有天气前置输入，符合规划里的 `itinerary_generation/v1`；当前 P3-02 代码已加入天气证据和活动调整提示，但尚未版本化。当前模板必须单独冻结为迁移/回滚基线，不能误标为 P2 v1。
- `MomaDayEditor` 在服务代码中内嵌编辑 Prompt。生成器只保留最后一次 `usage`，未按模型调用聚合；生成器和编辑解析失败的日志分别输出响应尾部或预览，不能作为 P3 脱敏日志基线。
- 当前 `PromptBuilder._json_contract()` 是手写示例，不能替代 `Itinerary`/`DayEditDraft` 的 Pydantic 校验。供应商不保证严格 JSON Schema 输出时，后端校验及 Critic 仍是硬门槛。

## 执行顺序

### 1. 冻结 Prompt 契约与旧版基线

1. 逐一列出模型调用点、输入、输出、校验器和修复次数：基础生成、JSON/结构修复、Critic finding 修复、单日编辑；标注 legacy 与 langgraph 各自调用路径。
2. 从 P2 历史提交冻结 `itinerary_generation/v1`（天气后置的旧 Prompt）；另将当前 P3-02 Prompt 冻结为具名兼容版本，保留其生成前天气行为。以当前版本为起点定义 `itinerary_generation/v2`，使用受控候选、逐日天气和检索证据。定义独立的 `structured_repair/v1`、`critic_repair/v1`、`day_edit/v1`；同一版本内容不可原地修改。
3. 为每个模板定义稳定 ID、版本、输入字段及上限、输出模型/Schema、适用运行时、事实优先级。生成输出只覆盖模型可填写字段；天气、坐标、核实状态、路线、图片等由后端写入。编辑输出对应 `DayEditDraft`，只允许目标日字段。
4. 明确缺少可信候选、天气 `unknown`、RAG 空命中时的输入语义；证据统一以有界 JSON 数据块传入，来源文本和用户备注均视为数据，不执行其中的指令。候选 ID、请求日期和预算优先于 RAG 与模型偏好。

交付：版本/输入/输出契约表、P2 v1 与当前 P3-02 的冻结快照，以及 Pydantic Schema 与模板声明不一致的清单。先记录现状，再改调用行为。

### 2. 建立注册表与结构化模板

1. 在 `backend/app/services/` 建立不可变模板注册表，按 `prompt_id/version` 显式查询；未知版本或必需输入缺失时稳定失败。把生成和编辑的内嵌文本移入各自模板，保留调用端只负责组装受控数据。
2. 模板分成 system、policy、evidence、output 四层；按当前 MoMA Chat Completions 能力映射角色，并记录模板的输出 Schema 版本。使用 Pydantic 导出或校验输出形状，避免另写一份会漂移的“完整 Schema”；示例仅辅助模型，不充当校验规则。
3. 对 POI、天气和 RAG 证据做数量/长度限制、确定性排序和 JSON 序列化；保留 `chunk_id/source/source_version`，天气按日期键传递，候选只暴露可信 ID。截断须产生可观测的计数，不能静默改变硬约束。
4. 提供独立版本选择配置，langgraph 默认先维持当前 P3-02 兼容版本，允许灰度选 v2；legacy 可继续选 P2 v1。修复和编辑分别选版。版本配置与 `AGENT_RUNTIME` 分开，两条编排路径各自有可运行回滚版本，公开 API 不增加版本字段。

交付：注册表、模板、版本选择和契约测试；`PromptBuilder` 与 `MomaDayEditor` 接入注册表。

### 3. 统一修复调用与硬校验

1. 将“模型调用”作为修复次数的计量单位：首次生成后，结构修复与 Critic 修复共用一次默认修复预算。图节点必须调用相应的修复模板，并提供原草稿、脱敏/结构化错误代码与字段路径；不再把修复节点当作无区别的全量生成。
2. 对 legacy 明确内部修复仍最多一次；对 langgraph 避免生成器内部修复叠加图修复。模型超时、无输出、非法 JSON、Pydantic 拒绝和 Critic 拒绝分别走现有稳定错误边；不可修复失败不反复请求模型。
3. 修复输入中的原始模型文本只在内存中按长度限制传给修复模板，不进入日志、trace 或评测报告。Critic finding 仅传 `code/path` 与经过审核的简短规则说明，不传供应商响应或异常原文。
4. 每次修复后完整重跑 `TripService` 结构、日期、费用、候选 ID 校验，再经天气权威回填和 Critic；单日编辑保留现有目标日范围、版本冲突和写库前校验。

交付：两类修复的独立调用路径、共享次数预算及正常/拒绝/超限回归测试。若改变图状态或节点契约，更新 `graph_version` 与 `docs/orchestration.md`。

### 4. 脱敏执行元数据与观测

1. 每次模型调用记录请求 ID、运行时、图版本、Prompt ID/版本、输出 Schema 版本、模型 ID、调用阶段、耗时、token 使用量、校验结果和稳定错误码。请求结束聚合各阶段 token/耗时，不能只读取生成器最后一次 `usage`。
2. 证据只记录计数、天气日期覆盖数、可信 POI 数、RAG 片段数及来源类型；不得记录完整 Prompt、用户备注、原始模型输出、供应商响应、密钥或可还原这些内容的预览。移除现有响应 `tail`/`preview` 日志；验证 Pydantic 错误只输出字段路径和类型。
3. 保持 trace 为节点级脱敏摘要，模型调用元数据通过请求级观测关联；不要把内部 Prompt、模板正文或原始证据加进 HTTP 响应或 SQLite 行程版本。

交付：结构化元数据记录及敏感字符串哨兵测试，覆盖成功、解析失败、修复和编辑路径。

### 5. 固定评测集和 A/B 运行器

1. 建立匿名、可提交的离线 fixture：3/4/7 天、预算边界、完整/部分/未知天气、可信候选充足/不足、RAG 空命中、恶意证据文本、结构损坏、Critic finding、单日编辑越界。固定请求、证据、模型参数和期望规则，不使用真实用户内容或供应商密钥。
2. A/B 在相同 langgraph 运行时、相同证据和模型配置下只切换生成 Prompt：比较 P2 v1、当前 P3-02 兼容版本与目标 v2。v1 忽略天气证据是模板本身的预期差异；v2 必须同时对照当前兼容版本，避免把 P3-02 已有收益当作新改进。单独评估 `structured_repair/v1`、`critic_repair/v1` 和 `day_edit/v1`。legacy 对照只用于 HTTP/存储兼容。
3. 离线回放保存按版本采集且脱敏的模型输出 fixture，运行真实解析器、Pydantic、候选校验、天气回填及 Critic。Fake 响应验证流程可重复性；单靠 fake 不能证明 v2 的模型质量改善，切默认版前另做同模型、同参数、成对样本的受控调用并把输出转成可回放 fixture。
4. 每条样本同时输出首次结构通过、最终通过、日期/预算错误、可信候选 ID 命中、天气适配、修复结果、调用次数、token、耗时和降级原因。定义天气适配为活动选择符合可信同日天气的人工标注/规则断言，`unknown` 不计作晴天；报告分母、样本数、每个分层和总体结果。
5. 先采集 v1 和当前 P3-02 基线并锁定样本与门槛，再跑 v2；发布门槛至少需要 12 个不同场景的同配置成对模型样本。重复采样可用于观察波动，但不增加不同场景数。失败样本保留 fixture ID、Prompt 版本、校验 finding 和复现命令，不保留原始敏感文本。运行器以非零退出码表示硬门槛失败，报告可供 CI 与人工复核。

交付：fixture、离线评测命令、A/B 差异报告格式及 v1/当前 P3-02 基线报告。受控模型采样是切版验收项，不纳入默认 CI。

### 6. 验收门槛与发布/回滚

| 门槛 | 判定方法 |
| --- | --- |
| 硬约束 | 所有 fixture 的 HTTP/SQLite 契约兼容；未校验行程返回数、越界编辑写入数、伪造天气事实数及非可信候选 ID 通过数均为 0。 |
| 首次生成 | v2 首次结构通过率、日期与预算正确率不低于同集 v1 和当前 P3-02 兼容版本；逐项列出失败样本，不用最终修复成功掩盖首次失败。 |
| 证据使用 | v2 的可信候选 ID 命中率、已知恶劣天气适配率不低于当前 P3-02 兼容版本；`unknown` 日期不产生天气事实；部分覆盖与降级均能完成受规则保护的生成。 |
| 修复 | 结构与 Critic 修复共用默认最多一次额外模型调用；超限稳定报错，修复后必须重新通过全部校验。 |
| 成本与延迟 | 报告每阶段及总 token、P95 生成耗时和降级率；v2 总 token 与 P95 均不超过当前 P3-02 兼容版本的 1.2 倍，超出则维持当前版本并分析样本。统计口径和样本数随报告固定。 |
| 脱敏 | 所有路径的日志、trace 和评测报告均无 Prompt 全文、密钥、用户备注及供应商/模型原始响应片段。 |

先运行模板/解析/修复/编辑的针对性测试与离线评测，再运行 `python -m pytest -q`、`python -m ruff check .` 和 `python -m ruff format --check .`。仅当硬门槛、同配置 A/B 与成本门槛均通过，才把 langgraph 默认生成版本切到 v2；否则维持当前 P3-02 兼容版本并保留失败报告。发布时记录实际 `prompt_id/version`、`graph_version` 与模型配置；回滚只切 Prompt 版本或 `AGENT_RUNTIME`，不改 SQLite 数据。

## 预期修改位置

- 模板与版本：`backend/app/services/prompt_builder.py`、新增 Prompt registry/模板模块、`backend/app/services/trip_edit.py`、`backend/app/config/settings.py`。
- 调用与观测：`backend/app/services/itinerary_generator.py`、`backend/app/services/langgraph_orchestration.py`、`backend/app/services/orchestration.py`、`backend/app/main.py`；必要时扩展 MoMA 结果的安全元数据接口。
- 测试与评测：`backend/tests/moma/`、`backend/tests/api/test_langgraph_orchestration.py`、`backend/tests/api/test_trip_edit.py`、`backend/tests/e2e/` 和独立的离线评测 fixture/运行器。
- 契约文档：实施后更新 `docs/orchestration.md`、`docs/trip-edit.md` 和验收记录；`docs/p3-plan.md` 继续作为范围基线。

## 本轮离线实施记录

- 已建立 `itinerary_generation/v1`、`itinerary_generation/p3-02-compat`、`itinerary_generation/v2`，以及 `structured_repair/v1`、`critic_repair/v1`、`day_edit/v1` 注册项。v2 使用 Pydantic 草稿 Schema；服务端天气、坐标、来源、路线等字段不能进入 v2 草稿。
- LangGraph 图版本为 `trip-generation/v2`；首次生成和每个修复节点各对应一次 MoMA 调用，结构与 Critic 修复共用默认一次预算。legacy 保留生成器内一次结构修复；两种运行时的默认生成 Prompt 分别为 P2 v1 和 P3-02 兼容版。
- 模型调用记录只包含版本、Schema、模型 ID、token、耗时、证据计数、校验状态与稳定错误码。生成器和编辑器的响应片段日志已移除；真实 Prompt 与模型原文不进入 trace 或评测报告。
- `python -m backend.eval.prompt_ab` 对匿名 3、4、7 天合成 fixture 执行三版本同图回放。当前 9 个回放组合均通过硬契约；报告明确 `release_gate_pass=false`，因为没有真实模型成对样本与可比较的 P95 延迟。
- 真实 A/B 的准备工作仍包括采集至少 12 个同模型、同参数、同证据的成对输出与用量/耗时。`p3_03_ab.json` 提供 13 个匿名场景，采样命令只接受合成 fixture，输出被 Git 忽略：

  ```powershell
  python -m backend.eval.prompt_ab --fixtures backend/eval/fixtures/p3_03_ab.json --capture-output backend/eval/captures/p3-03-paired.json
  python -m backend.eval.prompt_ab --fixtures backend/eval/captures/p3-03-paired.json --require-release-gate
  ```

  采样完成后需复核失败样本、来源脱敏和指标；报告不输出模型原文。真实门槛未完成前不修改默认版本。

### 本轮真实采样记录（2026-10-14）

- 已对 `deepseek-v4-flash-0731` 做真实请求探测：短探针可返回；完整 v2 首个场景在 `2048` 输出 token、`120` 秒请求上限下曾返回一次完整内容。
- 使用相同配置执行 13 个场景、三个 Prompt 版本的完整采样时，首个 P2 v1 请求在上限内超时或未返回最终回答；运行器因此没有写入部分捕获文件。
- 随后将本地配置切换为 `zhipu/glm-5.3-flash`，以 `8192` 输出 token、`300` 秒请求上限和一次客户端重试执行同一 13 场景采样。部分场景可以稳定返回，checkpoint 曾保存 13 个场景中的 27 个版本响应；剩余调用因供应商响应过慢或网络/无最终回答错误未完成。
- 真实采样因整体耗时过长已主动停止；当前没有完整的 12+ 场景成对模型样本，不能据此切换 v2。默认生成版本继续保持 `p3-02-compat`；`backend/eval/captures/` 中的 checkpoint 被 Git 忽略，不作为提交或发布依据。
