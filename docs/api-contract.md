# 当前 API 契约与 P2 扩展边界

本文档记录 2026-09-29 本地 `main`（`6f76009`）已有的旅行规划 API 以及 P2-01 冻结的身份、版本和预留接口契约。后端模型、路由、测试和 MoMA 生成结果以当前契约为准。字段删除或改名必须先经过团队评审；新增字段应保持向后兼容。

## `POST /api/trip/generate`

根据用户的目的地、日期和约束生成结构化旅行行程。

### 请求示例

```json
{
  "destination": "杭州",
  "start_date": "2026-10-01",
  "end_date": "2026-10-04",
  "travelers": 2,
  "budget": 10000,
  "preferences": ["美食", "历史文化"],
  "pace": "relaxed",
  "dietary_preferences": ["少辣"],
  "hotel_level": "four_star",
  "special_notes": "不要早起"
}
```

### 请求字段

| 字段 | 类型 | 必填 | 默认值 | 约束和说明 |
| --- | --- | --- | --- | --- |
| `destination` | string | 是 | — | 去除首尾空格后不能为空；第一版为单个城市或目的地。 |
| `start_date` | string | 是 | — | ISO-8601 日期，格式为 `YYYY-MM-DD`。 |
| `end_date` | string | 是 | — | ISO-8601 日期，格式为 `YYYY-MM-DD`，不能早于 `start_date`。 |
| `travelers` | integer | 否 | `1` | 必须大于等于 `1`。 |
| `budget` | number | 否 | `null` | 总预算金额；如果提供，必须大于等于 `0`。单位为人民币元。 |
| `preferences` | array[string] | 否 | `[]` | 旅行偏好；每项不能为空，第一版最多 10 项。 |
| `pace` | string | 否 | `null` | 允许值：`relaxed`（轻松）、`normal`（适中）、`intensive`（紧凑）。 |
| `dietary_preferences` | array[string] | 否 | `[]` | 饮食要求；每项不能为空，第一版最多 10 项。 |
| `hotel_level` | string | 否 | `null` | 允许值：`budget`、`three_star`、`four_star`、`five_star`、`不指定`。 |
| `special_notes` | string | 否 | `null` | 其他约束，去除首尾空格后不能为空；第一版最多 2000 个字符。 |

### 请求校验规则

- 行程天数按 `end_date - start_date + 1` 计算，第一版必须为 **3—7 天（含边界）**。
- 日期解析失败、日期顺序错误或行程天数不符合范围时，返回 `INVALID_TRIP_REQUEST`。
- `destination`、数组元素和 `special_notes` 均应在校验前去除首尾空格。
- `budget` 表示具体金额，不使用 `"low"`、`"medium"`、`"high"` 等预算等级字符串。
- `budget`、活动费用和总费用均使用非负数；金额单位为人民币元。
- 未提交的可选数组按空数组处理，未提交的可选标量按文档中的默认值处理。

## 响应

HTTP 状态码为 `200 OK` 时返回 `Itinerary`。`days` 必须覆盖请求日期范围内的每一天，日期连续且顺序与请求一致。

当前路由使用 `response_model_exclude_defaults=True`；等于模型默认值的可选字段可能在 HTTP JSON 中省略。下表的 `null`/空数组描述模型语义，不保证每次序列化都显式出现。

```json
{
  "destination": "杭州",
  "start_date": "2026-10-01",
  "end_date": "2026-10-04",
  "summary": "适合两人的轻松文化美食之旅",
  "days": [
    {
      "date": "2026-10-01",
      "title": "西湖与湖滨区域",
      "activities": [
        {
          "time": "09:00",
          "name": "西湖游览",
          "description": "环湖散步并游览断桥",
          "location": "西湖",
          "duration_minutes": 180,
          "estimated_cost": 0
        }
      ]
    }
  ],
  "total_estimated_cost": 1800
}
```

### 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `destination` | string | 与请求中的目的地保持一致。 |
| `start_date` | string | 行程开始日期。 |
| `end_date` | string | 行程结束日期。 |
| `summary` | string | 行程摘要，不能为空。 |
| `days` | array[DayPlan] | 按日期升序排列，必须覆盖完整请求日期范围。 |
| `days[].date` | string | 当天日期，格式为 `YYYY-MM-DD`。 |
| `days[].title` | string | 当天主题，不能为空。 |
| `days[].activities` | array[Activity] | 当天活动列表。 |
| `days[].activities[].time` | string | 建议使用 `HH:MM` 24 小时制。 |
| `days[].activities[].name` | string | 活动名称，不能为空。 |
| `days[].activities[].description` | string | 活动说明。 |
| `days[].activities[].location` | string/null | 活动地点。 |
| `days[].activities[].duration_minutes` | integer/null | 活动时长，提供时必须大于 `0`。 |
| `days[].activities[].estimated_cost` | number | 活动预计费用，必须大于等于 `0`。 |
| `days[].activities[].poi_id` / `poi_category` | string/null | 可选；经候选池或供应商核实的地点 ID 与分类（`spot`/`meal`/`hotel`）。 |
| `days[].activities[].poi_status` | string | `not_attempted`、`verified`、`not_found`、`ambiguous` 或 `unavailable`。 |
| `days[].activities[].address` / `latitude` / `longitude` / `map_source` | string/number/null | 可选的已核实地图信息，未知时不得伪造。 |
| `days[].activities[].route_status` / `route_from_previous` | string/object/null | 相邻活动的路线状态及供应商估算；见下文。 |
| `days[].weather` | object/null | 可选天气补充，按同一 `DayPlan.date` 对齐；天气服务失败时为 `null`，不影响基础行程。 |
| `days[].weather.status` | `available`/`unknown` | `available` 表示有供应商预报；`unknown` 表示超出预报覆盖范围或没有该日数据，不能解读为晴天。 |
| `days[].weather.condition` | string/null | 供应商返回的天气描述；未知时为 `null`。 |
| `days[].weather.low_celsius` | number/null | 最低温度（摄氏）；未知时为 `null`。 |
| `days[].weather.high_celsius` | number/null | 最高温度（摄氏）；未知时为 `null`。 |
| `days[].weather.source` | string/null | 数据来源标识，例如 `amap`。 |
| `days[].weather.fetched_at` | string/null | 获取时间（ISO-8601）；没有时为 `null`。 |
| `days[].weather_advice` | array[string] | 可选的轻量天气提示；不得删除、替换或重排行程。 |
| `total_estimated_cost` | number | 行程预计总费用，必须大于等于 `0`，且不能小于已列活动预计费用之和。可包含尚未单独列出的住宿、交通等费用。 |
| `map_enrichment_status` | string | `not_attempted`、`completed`、`partial` 或 `unavailable`。 |
| `trip_id` | string/null | P2 身份字段。旧版生成响应可以省略；保存或版本化操作必须提供。由服务端生成，不能由模型生成。 |
| `version` | integer/null | P2 版本字段，从 `1` 开始递增。旧版生成响应可以省略；保存或版本化操作必须提供。 |

第一版统一使用 `activities` 表示每日安排。景点、餐饮、住宿、交通、天气和预算拆分字段属于后续兼容扩展；新增这些字段不能改变现有字段含义。

## 错误响应

请求校验错误和已映射的 `TripServiceError` 使用以下结构，不向客户端返回 Python traceback、内部路径、完整 Prompt 或 API Key：

```json
{
  "code": "MOMA_INVALID_RESPONSE",
  "message": "MoMA 返回的行程无法通过结构校验",
  "request_id": "req_..."
}
```

### 第一版错误码和建议 HTTP 状态

| 错误码 | HTTP 状态 | 使用场景 |
| --- | ---: | --- |
| `INVALID_TRIP_REQUEST` | `422` | 请求字段缺失、类型错误、日期错误或约束不满足。 |
| `MOMA_TIMEOUT` | `504` | MoMA 请求超时且重试失败。 |
| `MOMA_INVALID_RESPONSE` | `502` | MoMA 返回内容不是可解析的 JSON 或缺少必要结构。 |
| `ITINERARY_VALIDATION_ERROR` | `502` | JSON 可解析，但不符合 `Itinerary` 字段或业务规则。 |
| `TRIP_NOT_FOUND` | `404` | 行程或指定版本不存在。 |
| `TRIP_VERSION_CONFLICT` | `409` | 客户端提交的预期版本不是当前版本；写入不会覆盖当前版本。 |
| `INVALID_TRIP_VERSION` | `422` | 版本号缺失、不是正整数或与请求体不一致。 |
| `INTERNAL_SERVER_ERROR` | `500` | 未预期的内部错误；不暴露供应商详情、Prompt、密钥或内部路径。 |

未预期异常统一返回上述结构和 `INTERNAL_SERVER_ERROR`。`/api/chat` 仍是无状态消息转发；供应商错误可以返回 HTTP `502`，但响应体使用 `INTERNAL_SERVER_ERROR`，不暴露供应商正文、密钥、Prompt 或内部路径。

## 生成器与服务边界

- 路由只负责 HTTP 输入输出，业务逻辑放在 `TripService`。
- `TripService` 接收经过校验的 `TripRequest`，调用可替换的行程生成器，并返回 `Itinerary`。
- 生成器至少应提供等价于以下接口的能力：

  ```python
  generate(request: TripRequest) -> str
  ```

- 生成器负责 MoMA Prompt、请求、重试以及必要的 Markdown 代码块剥离；`TripService` 负责最终 JSON 解析、Pydantic 校验和日期/费用等业务校验。
- MoMA 输出必须经过 JSON 解析和 `Itinerary` 校验后才能作为成功响应。
- 地图和天气作为可替换 integration，不直接耦合到 MoMA 客户端或路由。
- 所有请求应支持 `request_id` 追踪；内部错误不得泄露给用户。
- 新字段优先向后兼容，删除或改名必须经过 PR 评审。

## P2-01 行程身份与版本

### 身份规则

- `trip_id` 由后端服务在生成或首次保存时创建，格式由服务实现决定；MoMA 和其他模型不得生成或覆盖它。
- `version` 是从 `1` 开始的正整数。创建行程的初始版本为 `1`；每次成功写入新版本后递增 `1`。
- 旧版 `POST /api/trip/generate` 的请求格式保持不变；其原有必填响应字段保持不变，`trip_id` 和 `version` 可以在兼容阶段省略。
- 保存、编辑、历史和导出使用服务端存储的完整 `Itinerary` 版本，不接受客户端通过修改模型字段伪造当前版本。
- 任何版本化写操作必须携带 `expected_version`；服务端仅在它等于当前版本时写入并递增版本。冲突写入不得覆盖已有版本。

### 保存与历史接口（P2-04 实现）

```text
POST   /api/trip/save
GET    /api/trip
GET    /api/trip/{trip_id}
GET    /api/trip/{trip_id}/versions
DELETE /api/trip/{trip_id}
```

保存请求：

```json
{
  "itinerary": {
    "trip_id": null,
    "version": null,
    "destination": "杭州",
    "start_date": "2026-10-01",
    "end_date": "2026-10-03",
    "summary": "杭州三日游",
    "days": [
      {
        "date": "2026-10-01",
        "title": "待规划",
        "activities": []
      }
    ],
    "total_estimated_cost": 0
  },
  "expected_version": null
}
```

- `trip_id` 和 `version` 都为空表示创建新行程；服务端生成 ID 并保存为版本 `1`。
- 已有行程必须提供 `itinerary.trip_id` 和 `expected_version`；成功后返回递增版本。
- 保存响应返回带有 `trip_id` 和 `version` 的完整 `Itinerary`。
- `GET /api/trip` 返回有界的 `TripListResponse`，按更新时间倒序；使用 `limit` 和不透明 `cursor` 分页时不得无限返回历史。
- `GET /api/trip/{trip_id}` 返回当前版本的完整 `Itinerary`。
- `GET /api/trip/{trip_id}/versions` 返回 `TripVersionsResponse`；版本顺序和当前版本语义必须稳定。
- 删除成功后该行程及其版本不可再通过这些接口读取，重复读取返回 `TRIP_NOT_FOUND`。

### 单日编辑接口基础契约（P2-05 消费）

```text
POST /api/trip/{trip_id}/edit
```

请求体：

```json
{
  "expected_version": 1,
  "date": "2026-10-02",
  "instruction": "减少当天活动，并增加海边日落"
}
```

编辑服务只允许修改指定 `date`，保持目的地、请求日期范围、其他日期和已确认硬约束不变；成功写入新版本并返回 `trip_id`、新 `version`、完整行程和 `change_summary`。编辑算法、Prompt 和局部差异校验由 P2-05 负责。

### 导出接口基础契约（P2-09 消费）

```text
GET /api/trip/{trip_id}/export?version=2&format=markdown
```

- `format` 只允许 `markdown` 或 `pdf`。
- `version` 可选；省略时导出当前版本。指定不存在的版本返回 `TRIP_NOT_FOUND`。
- 导出固定读取服务端保存的版本，不重新生成或修改行程。
- Markdown 使用 `text/markdown; charset=utf-8`；PDF 使用 `application/pdf`。
- 下载文件名只使用服务端生成的安全名称；内容不得包含 Prompt、API Key、内部日志或本机路径。

### 错误响应示例

```json
{
  "code": "TRIP_VERSION_CONFLICT",
  "message": "行程已被其他请求更新，请重新读取最新版本",
  "request_id": "req_..."
}
```

## P1 地图与天气接入约束

当前 `POST /api/trip/generate` 在基础行程通过校验后依次调用地图和天气补全。所有新增字段均为向后兼容字段；没有地图或天气 Key、搜索或预报失败时保留基础行程。供应商适配器内部有 `MAP_SERVICE_ERROR`/`WEATHER_SERVICE_ERROR` 类型，但当前生成端点将这些可选补全失败降级处理，不以这两个错误码响应。

## P2-02 城市解析与候选池

候选池在进入 MoMA Prompt 前建立，作为模型可选择地点的唯一来源。城市解析不依赖模型：

- 已知别名（例如“杭州市”“西湖区”）归一化为单一城市名；未登记但不是省级范围的输入标记为 `dynamic`，保留原城市文本。
- 省级输入（例如“浙江省”）标记为 `insufficient_data`，因为当前候选池要求单城市范围；不能用省级结果冒充城市规划。
- 每个候选必须有非空供应商 ID、名称、合法经纬度，并且显式供应商城市不能与目标城市冲突。没有城市元数据时，地址必须包含目标城市；无法满足条件的结果被丢弃并计入拒绝数。
- 候选按 `spot`、`meal`、`hotel` 分类去重。默认每类至少需要 1 个候选；分类不足、城市范围不合格或地图服务失败时，候选池将 `meets_minimum=false`，生成器回退到不带候选约束的基础行程，不伪造地点。

候选池向后续编排提供 `coverage_status`、各分类计数、`shortages`、`rejected_count` 和 `unavailable_reason`。这些是内部服务状态；对外 API 仍返回通过 P0 校验的基础行程，除非后续编排 Issue 明确定义新的业务错误响应。

### 地点与路线

- POI ID、地址和坐标必须来自可核实的高德搜索结果；匹配失败、结果歧义或缺少坐标时，不能把活动标记为已核实。
- 路线估算必须有可靠起终点坐标，并保留交通方式、距离及耗时来源；无路线时不得推算成高德结果。
- `Activity.poi_status` 可为 `not_attempted`、`verified`、`not_found`、`ambiguous` 或 `unavailable`；已核实时填充 `poi_id`、`address`、`latitude`、`longitude` 和 `map_source`。
- `Activity.route_status` 可为 `not_attempted`、`verified`、`missing_coordinates` 或 `unavailable`；路线结果放在 `route_from_previous`，包含 `mode`、`distance_meters`、`duration_seconds` 和 `source`。
- `Itinerary.map_enrichment_status` 可为 `not_attempted`、`completed`、`partial` 或 `unavailable`。
- POI 匹配只接受唯一的规范化名称精确匹配，不因名称相似而猜测；零结果、歧义、部分补全和地图服务错误均保留基础行程并区分状态。

### 天气与建议

- 预报按日期映射到行程；天气可用时标明数据来源，`fetched_at` 当前可为 `null`。高德天气客户端最多请求 4 天，行程允许 3 至 7 天；覆盖范围取决于请求日期与供应商返回日期的交集，不能保证任意 3～4 天行程都有预报。
- 雨天等建议必须依据实际预报，不得把天气未知解释为晴天，也不能凭天气推断景点营业状态。
- 天气不可用时保留基础行程；当前可选天气、建议和缺失状态字段的日期对齐与兼容行为见上文。

地图业务接入采用可选补全降级策略：服务错误映射为 `unavailable` 状态并返回基础行程；天气服务失败时 `weather` 为 `null`，`weather_advice` 为空数组。

## 其他当前路由与 P2 预留

- `GET /health` 返回 `{"status":"ok"}`，表示进程存活，不是外部供应商就绪检查。
- `POST /api/chat` 接受 `messages`、`max_tokens`、`temperature`、`top_p` 并转发给 MoMA；不产生 `Itinerary`、行程 ID 或持久化上下文。
- 保存、列表、详情、删除、单日编辑、会话、导出、Agent 轨迹和独立天气查询路由目前均不存在。P2-01 先定义这些新增接口的 ID、版本、冲突与错误结构；后续 Issue 不得直接复制参考项目的 `/trip/*` 路径或模型。
