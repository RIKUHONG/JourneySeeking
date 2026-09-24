# 第一版 API 契约

## `POST /api/trip/generate`

### 请求

```json
{
  "destination": "杭州",
  "start_date": "2026-10-01",
  "end_date": "2026-10-04",
  "travelers": 2,
  "budget": "medium",
  "preferences": ["美食", "历史文化"],
  "pace": "relaxed"
}
```

必填字段：`destination`、`start_date`、`end_date`。日期使用 ISO-8601 的 `YYYY-MM-DD`。`travelers` 默认值为 `1`，必须大于等于 `1`。`preferences` 默认值为空数组。

### 响应

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

### 错误响应

```json
{
  "code": "MOMA_INVALID_RESPONSE",
  "message": "MoMA 返回的行程无法通过结构校验",
  "request_id": "req_..."
}
```

第一版错误码：

```text
INVALID_TRIP_REQUEST
MOMA_TIMEOUT
MOMA_INVALID_RESPONSE
ITINERARY_VALIDATION_ERROR
MAP_SERVICE_ERROR
WEATHER_SERVICE_ERROR
INTERNAL_SERVER_ERROR
```

## 设计原则

- 路由只负责 HTTP 输入输出，业务逻辑放在 service 层；
- MoMA 输出必须经过 JSON 解析和 Pydantic 校验；
- 地图和天气作为可替换 integration，不直接耦合到 MoMA 客户端；
- 新字段优先向后兼容，删除或改名必须经过 PR 评审；
- `days` 的日期范围应覆盖请求的出行日期，具体校验由行程服务负责。
