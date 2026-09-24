# 觅旅 · MoMA 多模型智能旅行规划平台

## 软件开发文档

文档版本：V1.0  
编制日期：2026-09-23  
项目类型：移动云杯参赛项目  
参考项目：`tutu-zzz/zhilv-yuntu`  
目标平台：移动云 MoMA

---

## 1. 文档说明

### 1.1 编写目的

本文档用于指导“觅旅 · MoMA 多模型智能旅行规划平台”的产品设计、技术开发、测试验收、部署上线和比赛答辩。

文档覆盖以下内容：

- 项目背景与建设目标；
- 用户需求和业务范围；
- MoMA 平台能力映射；
- 系统总体架构；
- 多模型调度方案；
- Agent 编排和工具调用方案；
- 上下文管理方案；
- RAG 知识库方案；
- 数据模型和接口设计；
- 前后端开发要求；
- 测试、部署、监控和安全要求；
- 项目进度、验收标准和比赛演示方案。

### 1.2 术语定义

| 术语 | 说明 |
|---|---|
| MoMA | 移动云提供的多模型管理、调度、智能路由和上下文管理平台，具体接口以赛事方实际开放能力为准 |
| Agent | 能够理解目标、拆解任务、调用工具并完成业务流程的智能执行单元 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| POI | Point of Interest，地图兴趣点，例如景点、餐厅、酒店 |
| Trip | 一次完整的旅行规划任务 |
| Itinerary | 结构化旅行行程，包括日期、景点、餐饮、住宿、交通和预算 |
| Context | 用户会话、偏好、行程状态、工具结果和历史摘要等上下文信息 |
| Critic Agent | 对生成结果进行事实、结构、约束和业务规则校验的 Agent |
| Fallback | 主模型、外部服务或智能流程失败后的备用处理路径 |

### 1.3 参考资料

- `tutu-zzz/zhilv-yuntu` 项目源代码和 README；
- 移动云 MoMA 平台 API、SDK 和部署文档；
- 高德地图 Web 服务 API 文档；
- FastAPI、Pydantic、SQLAlchemy、Vue 3、Vite 官方文档；
- ChromaDB、LangChain、Redis、Docker Compose 文档。

> MoMA 的具体模型名称、API 路径、鉴权方式、上下文接口和配额，以赛事方实际提供的版本为准。本文档对这些部分采用适配层设计，禁止将平台细节散落在业务代码中。

---

## 2. 项目概述

### 2.1 项目名称

觅旅 · MoMA 多模型智能旅行规划平台。

### 2.2 项目定位

本项目面向中文旅游规划场景，利用移动云 MoMA 的多模型调度、智能路由和上下文管理能力，构建能够调用地图、天气、POI 和本地知识库的旅行规划 Agent。

系统不是简单的问答机器人，而是一个包含真实数据查询、约束推理、预算计算、路线规划、结果校验和多轮修改能力的业务型 Agent 系统。

### 2.3 建设目标

系统应支持用户通过自然语言或表单输入：

- 目的地；
- 出行日期；
- 出行人数；
- 总预算；
- 旅行偏好；
- 行程节奏；
- 饮食要求；
- 酒店偏好；
- 特殊约束。

系统根据输入自动完成：

1. 目的地解析和城市覆盖判断；
2. 用户意图和约束提取；
3. 本地旅游知识检索；
4. 高德 POI、地图和天气查询；
5. 景点、餐饮、酒店候选筛选；
6. 每日路线和行程安排；
7. 预算拆分和超预算提醒；
8. 结构化行程生成；
9. 事实、结构和业务约束校验；
10. 多轮自然语言修改和局部重规划；
11. 行程保存、历史查看和文档导出。

### 2.4 核心价值

- 通过 MoMA 将不同复杂度的任务路由到合适模型，降低成本并改善延迟；
- 通过上下文管理保持用户偏好、已确认约束和行程版本；
- 通过真实 POI ID 和后端校验减少模型幻觉；
- 通过 RAG 使用城市攻略和本地知识，提升中文旅游场景准确性；
- 通过天气、路线、预算等工具调用形成可执行方案；
- 通过多级降级保证外部服务或模型异常时仍可返回可用结果。

---

## 3. 业务范围

### 3.1 V1.0 必须实现

- [ ] 单城市旅行规划；
- [ ] 3—7 天行程生成；
- [ ] 景点、餐饮、酒店和交通安排；
- [ ] 预算拆解；
- [ ] 地图路线展示；
- [ ] 天气查询和天气适配建议；
- [ ] 本地攻略 RAG；
- [ ] 至少两个 MoMA 可调度模型或模型能力；
- [ ] Agent 工具调用；
- [ ] 多轮自然语言修改；
- [ ] 上下文记忆和行程版本；
- [ ] 行程保存、历史列表和查看；
- [ ] Markdown、PDF 导出；
- [ ] 模型或外部 API 失败降级；
- [ ] MoMA 调用、路由、延迟和 Token 统计。

### 3.2 V1.0 暂不实现

- [ ] 真实门票或酒店库存预订；
- [ ] 支付和退款；
- [ ] 完整用户社交关系；
- [ ] 多省跨城市超长行程自动执行；
- [ ] 机票、火车票自动出票；
- [ ] 酒店实时可订状态承诺；
- [ ] 面向大规模公众用户的复杂会员体系。

### 3.3 后续扩展

- 多人偏好冲突协调；
- 亲子、老人、情侣、摄影、自驾等旅行模板；
- 实时拥堵和景区客流接入；
- 节假日和营业时间动态调整；
- 多方案对比和预算优化；
- 用户画像和长期旅行偏好；
- 小程序、H5 和移动端适配；
- 运营后台和知识库管理后台。

---

## 4. 用户角色和典型场景

### 4.1 用户角色

| 角色 | 权限和职责 |
|---|---|
| 普通游客 | 创建、查看、编辑、保存和导出自己的旅行行程 |
| 参赛演示用户 | 使用预置场景演示 MoMA 路由、Agent 和上下文能力 |
| 知识库维护人员 | 管理城市攻略、标签、版本和知识库索引 |
| 系统管理员 | 查看模型调用、错误、延迟、成本和系统健康状态 |

### 4.2 典型场景

#### 场景 A：亲子出游

用户输入：

> 我和两个孩子准备去厦门玩 5 天，预算 10000 元，节奏轻松，不要早起，想看海边日落。如果下雨，自动换成室内活动。

系统应：

- 识别亲子、预算、轻松节奏、不可早起、海边日落和雨天替代等约束；
- 使用轻量模型抽取参数；
- 调用 RAG 检索厦门亲子和海边攻略；
- 调用 POI、路线和天气工具；
- 使用高质量规划模型生成五天行程；
- 用 Critic Agent 校验预算、密度和特殊要求；
- 在用户后续修改时保留上述硬约束。

#### 场景 B：多轮修改

用户输入：

> 第三天不要安排太多活动，并增加海边日落。

系统应只修改第三天，保留其他日期、预算、酒店和已确认约束，并记录行程版本。

#### 场景 C：天气触发重规划

用户输入：

> 明天下雨，把户外活动换成室内活动。

系统应查询天气，识别受影响的户外活动，仅调整相关日期和景点，并给出调整原因。

---

## 5. 总体技术架构

### 5.1 架构分层

```text
Vue 3 / TypeScript / Ant Design Vue
        ↓
Axios API Client
        ↓
Nginx / API Gateway
        ↓
FastAPI 业务后端
        ↓
Trip Orchestrator Agent
        ├── Intent Agent
        ├── Destination Agent
        ├── Retrieval Agent
        ├── POI Agent
        ├── Route Agent
        ├── Weather Agent
        ├── Budget Agent
        ├── Planner Agent
        └── Critic Agent
        ↓
移动云 MoMA
        ├── 多模型调度
        ├── 智能路由
        ├── 上下文管理
        ├── 模型降级
        └── 调用统计
        ↓
工具层
        ├── 高德地图和 POI
        ├── 高德天气
        ├── Chroma RAG
        ├── Redis Cache
        ├── 预算计算
        └── 行程校验
        ↓
SQLite / MySQL + ChromaDB + Redis
```

### 5.2 推荐技术栈

| 层次 | 技术选型 |
|---|---|
| 前端 | Vue 3、TypeScript、Vite、Ant Design Vue、Axios |
| 后端 | Python 3.11、FastAPI、Uvicorn |
| 数据模型 | Pydantic 2 |
| ORM | SQLAlchemy 2 |
| 关系数据库 | V1.0 使用 SQLite，生产扩展可使用 MySQL 或 PostgreSQL |
| AI 编排 | 移动云 MoMA + LangChain 适配层 |
| 向量库 | ChromaDB，生产可替换为移动云托管向量服务 |
| 缓存 | Redis |
| 外部服务 | 高德地图 Web 服务、高德天气服务 |
| 文档导出 | ReportLab、Markdown |
| 部署 | Docker、Docker Compose、Nginx |
| 测试 | Pytest、前端类型检查、接口测试、场景评估 |

### 5.3 推荐目录结构

```text
backend/
├── app/
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   ├── agents/
│   │   ├── orchestrator_agent.py
│   │   ├── intent_agent.py
│   │   ├── planner_agent.py
│   │   ├── critic_agent.py
│   │   └── tools/
│   ├── platform/
│   │   ├── moma_client.py
│   │   ├── model_router.py
│   │   ├── context_manager.py
│   │   └── observability.py
│   ├── rag/
│   │   ├── vector_db.py
│   │   ├── retriever.py
│   │   ├── reranker.py
│   │   └── knowledge_validation.py
│   ├── services/
│   │   ├── trip_service.py
│   │   ├── map_service.py
│   │   ├── weather_service.py
│   │   ├── budget_service.py
│   │   ├── validation_service.py
│   │   ├── storage_service.py
│   │   └── export_service.py
│   ├── models/
│   │   ├── schemas.py
│   │   └── db_models.py
│   └── config.py
├── data/
├── scripts/
├── tests/
└── requirements.txt

frontend/
├── src/
│   ├── components/
│   ├── views/
│   ├── services/
│   ├── stores/
│   ├── types/
│   └── App.vue
├── Dockerfile
├── nginx.conf
└── package.json
```

---

## 6. MoMA 平台能力设计

### 6.1 MoMA 能力映射

| 业务需求 | MoMA 能力 | 设计要求 |
|---|---|---|
| 意图抽取 | 多模型调度 | 优先使用低延迟、低成本模型 |
| 查询改写 | 智能路由 | 根据查询复杂度和语言长度选择模型 |
| 长行程规划 | 高质量模型路由 | 多约束任务使用高质量模型 |
| 多轮编辑 | 上下文管理 | 保存用户偏好、硬约束和行程版本 |
| RAG 查询 | 模型协同 | Query Rewrite、Embedding、Rerank 分工 |
| 工具选择 | Agent 编排 | 由总控 Agent 决定是否调用地图、天气和 POI |
| 主模型故障 | 自动降级 | 主模型 → 备用模型 → 规则流程 |
| 成本优化 | 路由策略 | 简单任务不得默认调用高成本模型 |
| 质量控制 | 多模型协作 | Planner 生成，Critic 校验 |
| 过程可追踪 | 调用日志 | 记录模型、路由原因、延迟、Token 和错误 |

### 6.2 MoMA 适配层原则

业务代码不得直接依赖具体 MoMA SDK 细节。统一通过以下接口访问：

```python
class MomaClient:
    def chat(self, task_type, messages, route_context=None): ...
    def generate_structured(self, task_type, schema, payload, route_context=None): ...
    def get_context(self, session_id): ...
    def append_context(self, session_id, item): ...
    def summarize_context(self, session_id): ...
```

如果 MoMA 实际提供的是 HTTP API，则由 `moma_client.py` 封装；如果提供 SDK，则由同一适配层封装。上层 Agent 不应感知底层调用方式。

### 6.3 模型角色

| 模型角色 | 典型任务 | 路由原则 |
|---|---|---|
| Fast Model | 参数抽取、分类、简单摘要 | 低延迟、低成本 |
| General Model | 查询改写、普通问答、轻量编辑 | 质量和成本平衡 |
| Planner Model | 多日行程和多约束规划 | 质量优先 |
| Long Context Model | 长历史、长攻略和上下文摘要 | 上下文容量优先 |
| Embedding Model | 文档和查询向量化 | 稳定性和吞吐优先 |
| Rerank Model | 候选片段重排序 | 相关性优先 |
| Critic Model | 质量和约束检查 | 可靠性优先 |
| Fallback Model | 主模型失败兜底 | 可用性优先 |

### 6.4 路由输入

路由器至少应接收：

```json
{
  "task_type": "trip_generation",
  "complexity": "high",
  "day_count": 5,
  "traveler_count": 3,
  "has_children": true,
  "has_budget_constraint": true,
  "context_tokens": 12000,
  "latency_budget_ms": 15000,
  "cost_budget": 0.08,
  "quality_requirement": "high",
  "primary_model_available": true
}
```

### 6.5 路由策略

```text
如果任务为参数抽取：Fast Model
如果任务为短文本查询改写：Fast Model 或 General Model
如果行程天数 >= 5 且存在多重约束：Planner Model
如果上下文超过阈值：Long Context Model 或先摘要
如果需要事实校验：Critic Model + 业务规则
如果主模型超时：切换备用模型
如果超出成本预算：压缩上下文并切换轻量模型
如果所有模型失败：使用规则版生成流程
```

### 6.6 路由可解释性

每次 MoMA 调用至少记录：

```json
{
  "request_id": "req_xxx",
  "task_type": "trip_generation",
  "selected_model": "planner-model",
  "route_policy_version": "v1",
  "route_reason": [
    "day_count >= 5",
    "has_budget_constraint",
    "quality_requirement = high"
  ],
  "fallback_chain": [
    "planner-model",
    "general-model",
    "rule-based-planner"
  ],
  "latency_ms": 8230,
  "prompt_tokens": 4200,
  "completion_tokens": 1100,
  "error": null
}
```

---

## 7. Agent 设计

### 7.1 Agent 总体编排

```text
用户请求
  ↓
Trip Orchestrator Agent
  ├── Intent Agent
  ├── Destination Agent
  ├── Retrieval Agent
  ├── POI Agent
  ├── Route Agent
  ├── Weather Agent
  ├── Budget Agent
  ├── Planner Agent
  └── Critic Agent
  ↓
结构化 Itinerary
```

### 7.2 Agent 职责

| Agent | 输入 | 输出 | 是否允许调用工具 |
|---|---|---|---|
| Intent Agent | 用户原始请求 | 结构化意图和约束 | 否 |
| Destination Agent | 目的地文本 | 标准城市、覆盖等级 | 行政区工具 |
| Retrieval Agent | 目的地、偏好、节奏 | RAG 片段 | 向量检索、Rerank |
| POI Agent | 候选 POI、偏好和预算 | POI ID 选择结果 | POI 查询、详情查询 |
| Route Agent | POI、日期和交通偏好 | 每日路线顺序 | 地图路线工具 |
| Weather Agent | 城市、日期 | 天气和风险 | 天气工具 |
| Budget Agent | 行程和预算 | 预算明细及风险 | 预算计算工具 |
| Planner Agent | 各 Agent 结果 | 完整 Itinerary | 可请求补充工具 |
| Critic Agent | Itinerary、约束和事实 | 校验报告 | POI、路线和规则校验 |
| Orchestrator Agent | 全部状态 | 执行计划和最终结果 | 允许调度子 Agent |

### 7.3 Agent 执行约束

- 每个 Agent 必须有固定输入和输出 Schema；
- Agent 不得直接修改其他 Agent 的上下文；
- 工具调用必须经过白名单和参数校验；
- 设置单次任务最大调用次数；
- 设置最大重试次数和总超时时间；
- Critic 失败后优先局部修复，避免全量重新生成；
- 所有 POI 必须通过候选池或地图服务校验；
- 所有预算合计由后端代码计算；
- 所有地图距离由地图工具计算，不由模型臆测。

---

## 8. 上下文管理设计

### 8.1 上下文分层

| 层级 | 内容 | 使用场景 |
|---|---|---|
| L0 | 当前用户输入 | 所有任务 |
| L1 | 最近对话摘要 | 多轮对话 |
| L2 | 用户偏好和硬约束 | 意图、规划、编辑 |
| L3 | 当前行程结构化状态 | 规划和局部修改 |
| L4 | 相关 RAG 片段 | 检索和规划 |
| L5 | 工具调用结果 | 规划、校验和重规划 |
| L6 | 历史对话归档 | 长期追溯和摘要 |

### 8.2 用户偏好上下文

```json
{
  "user_id": "user_001",
  "preferred_pace": "relaxed",
  "dietary_preferences": ["少辣"],
  "hotel_preference": "四星级",
  "avoid": ["早起", "长距离徒步"],
  "favorite_activity": ["日落", "摄影"],
  "updated_at": "2026-09-23T10:00:00Z"
}
```

### 8.3 行程上下文

```json
{
  "trip_id": "trip_001",
  "version": 3,
  "destination": "厦门",
  "confirmed_constraints": [
    "预算不超过 10000 元",
    "不要早起",
    "包含海边日落"
  ],
  "confirmed_pois": ["B010...", "B020..."],
  "current_itinerary": {},
  "parent_version": 2
}
```

### 8.4 上下文压缩策略

- 保留所有硬约束；
- 保留用户最新修改；
- 保留已确认的 POI、酒店和预算；
- 删除重复工具结果；
- 将旧对话压缩为摘要；
- 只保留与当前问题相关的 RAG 片段；
- 达到 Token 阈值时触发摘要模型；
- 记录上下文版本，避免旧结果覆盖新结果。

### 8.5 多轮编辑要求

用户修改行程时：

1. 解析修改范围；
2. 读取当前 itinerary 和硬约束；
3. 只重规划受影响的日期或字段；
4. 保留未修改内容；
5. 重新计算预算和路线；
6. 调用 Critic Agent；
7. 创建新版本；
8. 返回变更摘要。

---

## 9. RAG 知识库设计

### 9.1 知识源

V1.0 建议建设以下城市知识库：

- 北京；
- 成都；
- 厦门；
- 三亚；
- 大理；
- 西安；
- 上海；
- 杭州。

每个城市至少准备：

- 景点攻略；
- 美食攻略；
- 住宿区域；
- 交通建议；
- 季节信息；
- 亲子、情侣、老人等场景建议；
- 雨天备用方案；
- 预算参考。

### 9.2 文档切分

按 Markdown 二级、三级标题切分，每个 chunk 保存：

```json
{
  "id": "xiamen_guide_xxx",
  "title": "亲子景点",
  "text": "...",
  "source": "xiamen_guide.md",
  "destination": "厦门",
  "category": "attraction",
  "audience": ["亲子"],
  "season": "全年",
  "updated_at": "2026-09-23"
}
```

### 9.3 检索链路

```text
用户需求
  ↓
Query Rewrite
  ↓
目的地过滤
  ↓
Chroma 向量召回
  ↓
候选扩展
  ↓
MoMA 路由的 Rerank 模型
  ↓
规则级目的地和噪声过滤
  ↓
Planner 上下文
```

### 9.4 RAG 降级

- Chroma 不可用时回退到关键词检索；
- Embedding 不可用时使用关键词召回；
- Rerank 不可用时使用规则重排序；
- 目标城市无知识库时转入动态 POI 规划；
- 无法确认的信息不得作为事实输出。

---

## 10. 工具调用设计

### 10.1 工具清单

```text
resolve_destination
resolve_administrative_area
search_scenic_spots
search_restaurants
search_hotels
get_poi_detail
geocode_address
get_route
calculate_distance
calculate_travel_time
get_weather_forecast
retrieve_travel_guide
rerank_guide_chunks
calculate_budget
validate_itinerary
check_schedule_conflicts
save_itinerary
export_markdown
export_pdf
```

### 10.2 工具返回规范

成功返回：

```json
{
  "success": true,
  "data": {},
  "source": "amap",
  "cached": true,
  "timestamp": "2026-09-23T10:00:00Z",
  "error": null
}
```

失败返回：

```json
{
  "success": false,
  "data": null,
  "source": "amap",
  "cached": false,
  "error": {
    "code": "AMAP_TIMEOUT",
    "message": "地图服务请求超时",
    "retryable": true
  }
}
```

### 10.3 工具调用原则

- 模型负责决定是否需要工具；
- 工具负责提供真实数据；
- 业务代码负责关键计算和校验；
- 工具参数必须经过 Schema 校验；
- 工具必须有超时、重试和缓存；
- 工具必须限制调用次数；
- 工具错误不得直接暴露堆栈信息给用户。

---

## 11. 业务流程设计

### 11.1 生成行程主流程

```text
用户提交规划请求
  ↓
Intent Agent 提取参数和约束
  ↓
Destination Agent 标准化城市并判断覆盖等级
  ↓
选择本地 RAG 或动态 POI 分支
  ↓
Retrieval Agent 检索攻略
  ↓
POI Agent 获取并筛选真实候选
  ↓
Weather Agent 查询天气
  ↓
Route Agent 计算区域和路线
  ↓
Budget Agent 计算预算
  ↓
MoMA 路由 Planner Model
  ↓
生成结构化 Itinerary
  ↓
Critic Agent 校验
  ├── 通过：返回用户
  └── 不通过：局部修复后再次校验
```

### 11.2 已覆盖城市分支

```text
本地 Markdown 攻略
  ↓
Query Rewrite
  ↓
Chroma 检索
  ↓
Rerank
  ↓
Planner Model
  ↓
业务补全和校验
```

### 11.3 动态城市分支

```text
高德行政区解析
  ↓
搜索景点、餐饮、酒店候选
  ↓
候选数量和城市归属校验
  ↓
Planner 只输出候选 POI ID
  ↓
后端根据 POI ID 回填真实字段
  ↓
路线、天气、预算校验
```

### 11.4 多轮编辑流程

```text
用户编辑指令
  ↓
读取当前版本和硬约束
  ↓
识别修改范围
  ↓
局部调用 Agent
  ↓
重新计算预算和路线
  ↓
Critic 校验
  ↓
创建新版本并返回变更摘要
```

---

## 12. 数据模型设计

### 12.1 TripRequest

```json
{
  "destination": "厦门",
  "start_date": "2026-10-01",
  "end_date": "2026-10-05",
  "travelers": 3,
  "budget": 10000,
  "preferences": ["海边", "日落"],
  "pace": "轻松",
  "dietary_preferences": ["少辣"],
  "hotel_level": "四星级",
  "special_notes": "不要早起，如果下雨换成室内活动"
}
```

### 12.2 Itinerary

```json
{
  "trip_id": "trip_001",
  "version": 1,
  "destination": "厦门",
  "summary": "适合亲子和轻松节奏的厦门五日行程",
  "days": [],
  "estimated_budget": 9860,
  "budget_breakdown": {
    "transport": 1800,
    "hotel": 4200,
    "meals": 1800,
    "tickets": 1400,
    "other": 660,
    "total": 9860
  },
  "tips": [],
  "source_notes": [],
  "token_usage": {},
  "validation_status": "passed"
}
```

### 12.3 DayPlan

```json
{
  "day_index": 1,
  "date": "2026-10-01",
  "theme": "鼓浪屿轻松漫步",
  "spots": [],
  "meals": [],
  "hotel": {},
  "transport": [],
  "weather": {},
  "notes": [],
  "validation": {}
}
```

### 12.4 数据库表

建议至少包含：

```text
users
sessions
user_preferences
trip_records
trip_versions
context_items
tool_call_records
model_call_records
knowledge_documents
evaluation_cases
```

V1.0 可以先使用 SQLite，生产或多人并发环境迁移到 MySQL/PostgreSQL。

---

## 13. API 接口设计

### 13.1 旅行规划接口

```text
POST /api/trip/generate
```

请求体：`TripRequest`

返回体：`Itinerary`

### 13.2 多轮编辑接口

```text
POST /api/trip/edit
```

请求体：

```json
{
  "trip_id": "trip_001",
  "version": 1,
  "user_instruction": "第三天不要安排太多活动，并增加海边日落",
  "preserve_constraints": ["预算不超过10000元", "不要早起"]
}
```

### 13.3 行程保存和历史接口

```text
POST   /api/trip/save
GET    /api/trip
GET    /api/trip/{trip_id}
GET    /api/trip/{trip_id}/versions
DELETE /api/trip/{trip_id}
```

### 13.4 天气接口

```text
GET /api/weather/forecast?city=厦门&start_date=2026-10-01&end_date=2026-10-05
```

### 13.5 导出接口

```text
GET /api/export/{trip_id}/markdown
GET /api/export/{trip_id}/pdf
```

### 13.6 Agent 执行轨迹接口

```text
GET /api/trip/{trip_id}/trace
```

返回：

- Agent 执行顺序；
- 选择的模型；
- 工具调用；
- 每一步耗时；
- 校验结果；
- 降级记录。

该接口主要用于比赛演示和管理员观察，不应泄露敏感 Prompt 或密钥。

### 13.7 健康检查接口

```text
GET /health
GET /ready
```

`/health` 表示进程存活；`/ready` 检查 MoMA、Redis、数据库和关键外部服务是否满足运行条件。

---

## 14. 前端功能设计

### 14.1 页面清单

| 页面 | 主要功能 |
|---|---|
| 规划页 | 收集目的地、日期、预算、人数和偏好 |
| Agent 过程页 | 展示任务拆解、模型路由和工具调用 |
| 结果页 | 展示每日行程、预算、地图、天气和来源 |
| 编辑页 | 通过自然语言修改行程 |
| 历史页 | 查看、打开和删除历史行程 |
| 评估页 | 展示模型、路由、延迟和质量指标，比赛演示用 |
| 管理页 | 查看知识库、调用日志和错误，后续扩展 |

### 14.2 结果页必须展示

- 行程总览；
- 每日安排；
- 景点地址、坐标、图片和 POI ID；
- 餐厅和酒店来源；
- 交通路线和预计时间；
- 天气预报；
- 预算明细；
- 备用方案；
- 数据来源和更新时间；
- 规划过程和模型路由摘要；
- 不确定性提示。

### 14.3 Agent 过程展示

建议按时间线显示：

```text
✓ 完成目的地识别 —— Fast Model
✓ 检索厦门亲子攻略 —— Retrieval Agent
✓ 获取 18 个真实 POI —— 高德地图工具
✓ 查询 5 天天气 —— Weather Agent
✓ 生成多日行程 —— Planner Model
✓ 校验预算、路线和约束 —— Critic Agent
```

---

## 15. 非功能需求

### 15.1 性能目标

| 指标 | 目标 |
|---|---:|
| 简单参数抽取 P95 | ≤ 2 秒 |
| 普通行程生成 P95 | ≤ 20 秒 |
| 复杂行程生成 P95 | ≤ 40 秒 |
| 行程编辑 P95 | ≤ 15 秒 |
| API 错误率 | ≤ 1% |
| 缓存命中请求延迟 | ≤ 500 毫秒 |
| 单实例并发规划任务 | ≥ 5，按 MoMA 配额调整 |
| 健康检查响应 | ≤ 500 毫秒 |

### 15.2 质量目标

| 指标 | 目标 |
|---|---:|
| 结构化输出首次通过率 | ≥ 98% |
| POI 真实性率 | 100% 或明确标记待核实 |
| 目的地归属正确率 | ≥ 99% |
| 用户硬约束满足率 | ≥ 90% |
| 预算合计一致率 | 100% |
| 主模型失败降级成功率 | ≥ 95% |
| 多轮上下文保留准确率 | ≥ 95% |
| RAG Top-K 命中率 | 根据评估集设定，建议 ≥ 85% |

### 15.3 可维护性

- 模型、路由、Prompt 和工具配置分离；
- 所有外部服务均通过 Service 封装；
- 所有 Agent 均有独立测试；
- 所有接口均有 Schema；
- 所有关键链路有结构化日志；
- 所有模型调用支持 request_id 追踪；
- 所有路由策略带版本号；
- 禁止在业务代码中硬编码 API Key。

---

## 16. 测试计划

### 16.1 单元测试

- [ ] Pydantic 数据模型；
- [ ] 城市名称标准化；
- [ ] 预算计算；
- [ ] 日期和天数计算；
- [ ] 路线距离解析；
- [ ] POI 候选过滤；
- [ ] 上下文压缩；
- [ ] 行程版本控制；
- [ ] 结构化 JSON 解析；
- [ ] 错误码转换。

### 16.2 集成测试

- [ ] MoMA Client 连接；
- [ ] MoMA 多模型路由；
- [ ] MoMA 上下文读写；
- [ ] Chroma 检索；
- [ ] Redis 缓存；
- [ ] 高德地图；
- [ ] 高德天气；
- [ ] 数据库保存和读取；
- [ ] Markdown 和 PDF 导出。

### 16.3 场景测试

至少准备以下测试集：

1. 普通三日城市游；
2. 亲子五日游；
3. 老人慢节奏旅行；
4. 预算严格场景；
5. 少辣或特殊饮食场景；
6. 不想早起场景；
7. 日落和摄影偏好场景；
8. 雨天自动改方案；
9. 动态城市规划；
10. 连续三轮行程修改；
11. 主模型超时；
12. 高德 API 失败；
13. Redis 不可用；
14. Chroma 不可用；
15. 空目的地或省级目的地。

### 16.4 故障注入

- [ ] 主模型超时；
- [ ] 备用模型超时；
- [ ] MoMA 返回错误；
- [ ] Embedding 失败；
- [ ] Rerank 失败；
- [ ] 高德 API 限流；
- [ ] 高德 API 返回空结果；
- [ ] Redis 连接中断；
- [ ] 数据库不可写；
- [ ] 工具返回字段不完整；
- [ ] 用户输入 Prompt Injection。

---

## 17. 评估指标和对照实验

必须对比以下四种方案：

1. 单一通用模型；
2. 固定多模型；
3. MoMA 智能路由；
4. MoMA 智能路由 + 上下文管理 + Agent 校验。

建议统计：

| 指标 | 单模型 | 固定多模型 | MoMA 路由 | MoMA + 上下文 |
|---|---:|---:|---:|---:|
| 平均响应时间 |  |  |  |  |
| P95 响应时间 |  |  |  |  |
| 单次平均成本 |  |  |  |  |
| 结构化输出通过率 |  |  |  |  |
| 用户约束满足率 |  |  |  |  |
| POI 真实性率 |  |  |  |  |
| 多轮编辑成功率 |  |  |  |  |
| 主模型失败后的成功率 |  |  |  |  |
| RAG Top-K 命中率 |  |  |  |  |
| 工具调用平均次数 |  |  |  |  |

---

## 18. 安全、隐私和合规

- [ ] MoMA、地图和数据库密钥只放在后端环境变量；
- [ ] 禁止把 MoMA Token 暴露给浏览器；
- [ ] 用户输入设置长度和频率限制；
- [ ] 工具调用使用白名单；
- [ ] 工具参数使用 Schema 校验；
- [ ] 防止跨用户读取上下文；
- [ ] 日志脱敏，不记录完整隐私信息；
- [ ] 支持删除会话和用户偏好；
- [ ] 限制 Agent 最大循环次数；
- [ ] 限制单次任务最大 Token 和费用；
- [ ] 对旅游价格、库存、营业状态和天气信息标注更新时间；
- [ ] 明确门票、住宿和可订状态需要用户最终确认；
- [ ] 对模型生成内容标注“规划建议”，不作绝对承诺；
- [ ] 处理外部接口返回的恶意文本和 Prompt Injection。

---

## 19. 部署设计

### 19.1 Docker Compose 服务

```yaml
services:
  redis:
    image: redis:7-alpine

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - redis

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
```

### 19.2 环境变量

```text
MOMA_API_KEY=
MOMA_BASE_URL=
MOMA_PROJECT_ID=
MOMA_ROUTE_POLICY_ID=

LLM_MODEL=
EMBEDDING_MODEL=
RERANK_MODEL=

AMAP_API_KEY=
AMAP_BASE_URL=https://restapi.amap.com/v3

DATABASE_URL=sqlite:///db/app.db
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0

CHROMA_DB_DIR=db/chroma_db
CHROMA_COLLECTION_NAME=travel_guides

LOG_LEVEL=INFO
ENVIRONMENT=production
```

### 19.3 启动步骤

```text
1. 配置 backend/.env
2. 初始化数据库
3. 导入城市知识库
4. 执行 Chroma 入库脚本
5. 启动 Redis、后端和前端
6. 检查 /health 和 /ready
7. 验证 MoMA 调用
8. 验证高德地图和天气
9. 执行一条完整演示任务
```

### 19.4 上线前检查

- [ ] MoMA 项目和模型配额已确认；
- [ ] API Key 已配置；
- [ ] 高德 Key 已配置；
- [ ] 知识库已构建；
- [ ] Redis 已启动；
- [ ] 数据库已初始化；
- [ ] 健康检查通过；
- [ ] 日志可查询；
- [ ] 失败降级有效；
- [ ] 演示账号和数据已准备；
- [ ] 已准备 MoMA 不可用时的离线演示方案。

---

## 20. 项目开发计划

### 第 1 周：平台验证和详细设计

- [ ] 开通 MoMA 项目；
- [ ] 获取模型和接口清单；
- [ ] 跑通模型调用；
- [ ] 确认上下文 API；
- [ ] 确认路由能力；
- [ ] 完成总体架构和数据模型；
- [ ] 完成参赛 MVP 范围。

### 第 2 周：基础前后端

- [ ] 创建 FastAPI 项目；
- [ ] 创建 Vue 页面；
- [ ] 定义请求和响应 Schema；
- [ ] 实现基础单模型行程生成；
- [ ] 实现结果页。

### 第 3 周：MoMA 多模型调度

- [ ] 实现 MoMA Client；
- [ ] 实现任务分类；
- [ ] 实现模型路由；
- [ ] 实现路由日志；
- [ ] 实现备用模型；
- [ ] 增加路由过程展示。

### 第 4 周：RAG 和真实工具

- [ ] 整理城市攻略；
- [ ] 接入 Chroma；
- [ ] 接入 Query Rewrite 和 Rerank；
- [ ] 接入高德 POI、地图和天气；
- [ ] 实现真实 POI 回填。

### 第 5 周：Agent 和上下文

- [ ] 实现总控 Agent；
- [ ] 实现专业 Agent；
- [ ] 接入 MoMA 上下文；
- [ ] 实现上下文分层和压缩；
- [ ] 实现多轮修改；
- [ ] 实现行程版本。

### 第 6 周：校验、降级和评估

- [ ] 实现 Critic Agent；
- [ ] 实现结构和业务校验；
- [ ] 实现模型和工具降级；
- [ ] 完成场景测试；
- [ ] 完成基线对照实验；
- [ ] 生成质量、性能和成本报告。

### 第 7 周：部署和参赛材料

- [ ] Docker 化部署；
- [ ] 部署到移动云环境；
- [ ] 完成压力测试；
- [ ] 完成演示视频；
- [ ] 完成架构图和流程图；
- [ ] 完成答辩 PPT；
- [ ] 完成项目说明书和测试报告；
- [ ] 准备现场演示和离线备用方案。

---

## 21. 比赛演示方案

### 21.1 演示脚本

1. 用户输入一条复杂的亲子旅行需求；
2. 展示 Intent Agent 提取结构化约束；
3. 展示 MoMA 为简单任务选择快速模型；
4. 展示 RAG 检索和高德 POI 工具调用；
5. 展示天气查询；
6. 展示 MoMA 为复杂规划选择高质量模型；
7. 展示 Planner Agent 生成结构化行程；
8. 展示 Critic Agent 校验通过；
9. 展示地图、天气和预算结果；
10. 输入“第三天不要安排太多活动”；
11. 展示上下文识别和局部重规划；
12. 输入“明天下雨，调整户外活动”；
13. 展示天气驱动的动态改行程；
14. 模拟主模型失败，展示 MoMA 自动切换备用模型；
15. 展示最终行程保存和 PDF 导出。

### 21.2 必须体现的 MoMA 价值

- [ ] 同一业务流程中使用多个模型或模型能力；
- [ ] 模型选择不是固定写死，而是由任务特征触发；
- [ ] 能展示智能路由原因；
- [ ] 能展示多轮上下文保留；
- [ ] 能展示工具调用和 Agent 编排；
- [ ] 能展示模型失败后的自动降级；
- [ ] 能展示成本、延迟或质量的改进；
- [ ] 最终输出必须是可执行的业务结果，而非聊天文本。

---

## 22. 验收标准

### 22.1 功能验收

- [ ] 用户可以成功提交旅行规划请求；
- [ ] 系统可以生成结构化多日行程；
- [ ] 景点、餐厅和酒店可追溯到真实候选；
- [ ] 系统可以查询地图和天气；
- [ ] 系统可以拆分预算；
- [ ] 用户可以用自然语言编辑行程；
- [ ] 系统可以保留上下文和硬约束；
- [ ] 系统可以保存、查看和删除行程；
- [ ] 系统可以导出 Markdown 和 PDF；
- [ ] 系统可以展示 Agent 执行轨迹。

### 22.2 平台验收

- [ ] MoMA Client 可稳定调用；
- [ ] 至少完成两类模型或模型能力的调度；
- [ ] 有任务到模型的路由策略；
- [ ] 有上下文读写和摘要机制；
- [ ] 有失败重试和模型降级；
- [ ] 有模型调用日志；
- [ ] 有 Token、成本和延迟统计；
- [ ] 有基线对照实验。

### 22.3 可靠性验收

- [ ] 关键字段经过 Pydantic 校验；
- [ ] 预算合计由代码计算；
- [ ] POI 真实性得到后端校验；
- [ ] 外部 API 失败时有明确提示；
- [ ] 主模型失败时仍能返回降级结果；
- [ ] 上下文不会跨用户串线；
- [ ] Agent 不会无限循环调用工具。

---

## 23. 风险与应对

| 风险 | 影响 | 应对方案 |
|---|---|---|
| MoMA 接口与预期不一致 | 高 | 先做适配层和最小连通性验证 |
| 模型配额不足 | 高 | 轻量模型优先、缓存、限流和备用模型 |
| 外部地图接口不稳定 | 高 | Redis 缓存、重试、规则降级和演示数据 |
| LLM 生成虚假 POI | 高 | 候选 POI ID 约束、后端真实性校验 |
| 上下文过长 | 中 | 分层上下文、摘要和 Token 阈值压缩 |
| RAG 命中不准确 | 中 | metadata 过滤、Rerank、评估集和规则回退 |
| 规划耗时过长 | 中 | 并行工具调用、模型路由、缓存和局部重规划 |
| 比赛现场网络故障 | 高 | 准备离线演示数据和录屏 |
| 用户输入 Prompt Injection | 中 | 工具白名单、输入清洗和系统约束隔离 |
| 业务范围扩张过快 | 高 | 严格执行 V1.0 范围和验收标准 |

---

## 24. 结论

本项目的实现重点不是复制一个传统的旅游规划 Demo，而是围绕移动云 MoMA 构建一条可验证的 Agent 落地链路：

```text
真实用户需求
  ↓
意图识别和约束提取
  ↓
MoMA 智能路由
  ↓
专业 Agent 协作
  ↓
地图、天气、POI 和 RAG 工具调用
  ↓
结构化行程生成
  ↓
事实、预算、路线和约束校验
  ↓
上下文管理和多轮局部重规划
  ↓
可保存、可展示、可导出的业务结果
```

最终参赛项目应重点证明三件事：

1. MoMA 的多模型调度确实改善了质量、成本、延迟或稳定性；
2. 上下文管理让 Agent 能够在真实多轮业务中保持约束和状态；
3. Agent 能够调用真实工具并经过业务规则校验，输出可执行而不是只会聊天的旅行方案。

