# 当前 API 契约与 P2 扩展边界

本文档记录 2026-09-29 本地 `main`（`6f76009`）已有的旅行规划 API。后端模型、路由、测试和 MoMA 生成结果以当前契约为准。P2 接口尚未实现，具体路径和版本语义由成员 A 负责的 P2-01 契约 PR 确定，见 [P2 Issue 清单](p2-issues.md)。字段删除或改名必须先经过团队评审；新增字段应保持向后兼容。

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

未预期异常目前由 FastAPI 默认处理，尚不能保证返回上述结构或 `INTERNAL_SERVER_ERROR`。P2-01 需定义并测试统一 500 行为。`/api/chat` 的供应商错误也尚未纳入行程业务错误映射。

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

## P1 地图与天气接入约束

当前 `POST /api/trip/generate` 在基础行程通过校验后依次调用地图和天气补全。所有新增字段均为向后兼容字段；没有地图或天气 Key、搜索或预报失败时保留基础行程。供应商适配器内部有 `MAP_SERVICE_ERROR`/`WEATHER_SERVICE_ERROR` 类型，但当前生成端点将这些可选补全失败降级处理，不以这两个错误码响应。

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
