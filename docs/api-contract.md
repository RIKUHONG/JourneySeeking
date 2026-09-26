# 第一版 API 契约

本文档是第一版旅行规划 API 的对外契约。后端模型、路由、测试和 MoMA 生成结果都必须以本文档为准。字段删除或改名必须先经过团队评审；新增字段应保持向后兼容。

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
| `total_estimated_cost` | number | 行程预计总费用，必须大于等于 `0`，且不能小于已列活动预计费用之和。可包含尚未单独列出的住宿、交通等费用。 |

第一版统一使用 `activities` 表示每日安排。景点、餐饮、住宿、交通、天气和预算拆分字段属于后续兼容扩展；新增这些字段不能改变现有字段含义。

## 错误响应

所有业务错误使用统一结构，不向客户端返回 Python traceback、内部路径、完整 Prompt 或 API Key：

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
| `MAP_SERVICE_ERROR` | `502` | 地图或 POI 服务失败；接入地图后使用。 |
| `WEATHER_SERVICE_ERROR` | `502` | 天气服务失败；接入天气后使用。 |
| `INTERNAL_SERVER_ERROR` | `500` | 未预期的内部错误。 |

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

## P1 地图与天气接入约束（规划中，尚未实现）

当前 `POST /api/trip/generate` 不调用高德地图或天气服务，成功响应不包含 POI、路线、天气或补全状态字段。下面是成员 C 的两个 P1 Issue 的设计约束，不代表这些字段或行为已经上线。每个 Issue 在实现前须与成员 A 确认对外响应方式、更新本契约及测试，并保持现有请求与 `Itinerary` 必填字段向后兼容。

### 地点与路线

- POI ID、地址和坐标必须来自可核实的高德搜索结果；匹配失败、结果歧义或缺少坐标时，不能把活动标记为已核实。
- 路线估算必须有可靠起终点坐标，并保留交通方式、距离及耗时来源；无路线时不得推算成高德结果。
- 零搜索结果、部分补全和地图服务错误需要区分。约定为可选补全的部分应保留基础行程；若增加补全状态、告警或独立查询接口，须先定义其字段与错误行为。

### 天气与建议

- 预报按日期映射到行程，需说明数据来源及更新时间或可用范围。当前高德天气客户端支持 1 至 4 天，行程允许 3 至 7 天；超出预报范围的日期不能填入实时天气。
- 雨天等建议必须依据实际预报，不得把天气未知解释为晴天，也不能凭天气推断景点营业状态。
- 天气不可用时保留基础行程；若增加天气、建议或缺失状态字段，须先定义可选性、日期对齐和兼容行为。

`MAP_SERVICE_ERROR`、`WEATHER_SERVICE_ERROR` 目前是预留错误码。P1 接入时需明确哪些请求应返回 `502`，哪些请求返回基础行程与补全缺失信息；不能仅因适配器存在就宣称接口会返回这两个错误码。
