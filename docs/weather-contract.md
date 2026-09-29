# P1-3 天气接口契约

本契约记录 2026-09-29 `main` 已接入的按日天气补全。参考项目只用于设计对比，实际行为以本仓库代码和 [API 契约](api-contract.md) 为准。

## `DayPlan` 可选字段

```json
{
  "date": "2026-10-01",
  "title": "西湖",
  "activities": [],
  "weather": {
    "status": "available",
    "condition": "小雨",
    "low_celsius": 18,
    "high_celsius": 23,
    "source": "amap",
    "fetched_at": null
  },
  "weather_advice": ["建议携带雨具，路面湿滑时注意防滑。"]
}
```

`weather` 和 `weather_advice` 都是可选的；未接入或失败时，模型中的 `weather` 为 `null`、`weather_advice` 为空数组，所有既有 `activities` 原样保留。当前 HTTP 响应会省略等于默认值的字段，因此 `null`、空数组和 `fetched_at: null` 不一定在 JSON 中显式出现。

`weather.status` 取值如下：

- `available`：有供应商对该行程日的预报；`condition`、温度等字段可按实际数据填写。
- `unknown`：该日没有可用预报，尤其是超出供应商覆盖范围；不得填入推测的天气或温度。

## 日期映射和覆盖范围

- 唯一映射键是 `DayPlan.date` 与预报记录的 ISO-8601 `date`，按日历日期相等匹配。
- 不按数组下标、星期字符串或供应商返回顺序映射；每个行程日最多绑定一条天气记录。
- 当前高德适配器每次最多查询 4 天，但是否覆盖行程取决于行程日期与供应商返回日期的交集。不能保证未来任意 3～4 天行程全部有预报；没有同日记录的每一天都为 `unknown`。
- 当前业务层未填充 `fetched_at`，其值为 `null`；不能把示例时间当成已实现的供应商更新时间。

## 失败降级与建议边界

- 超时、配置错误、供应商错误、无效响应等天气失败不使 `POST /api/trip/generate` 失败；返回基础行程，天气字段保持 `null`/空提示。
- 雨天建议仅提供轻量、可解释的准备提示（雨具、防滑等）。天气第一版禁止自动删除、替换或重排行程；自动调度另行评审。
