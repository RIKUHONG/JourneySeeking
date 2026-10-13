# 天气接口契约：P2 基线与 P3 前置 7 天窗口

本契约记录 P2 已有的 `DayPlan` 天气字段和 P3-02 的当前实现。P2 历史实现使用高德在基础行程生成后补充天气，旧适配器技术上限为 4 天；P3-02 改用 Open-Meteo 逐日预报，LangGraph 在基础生成前查询完整请求日期范围（最多 7 天），legacy 运行时仍后置查询但也使用 Open-Meteo。

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
    "source": "Open-Meteo",
    "fetched_at": null
  },
  "weather_advice": ["建议携带雨具，路面湿滑时注意防滑。"]
}
```

`weather` 和 `weather_advice` 都是可选字段；当前生成链路的天气查询失败时逐日写入 `unknown`，`weather_advice` 为空数组。旧的已保存行程仍可能有 `weather: null`。HTTP 响应可能省略等于默认值的字段。

`weather.status` 取值如下：

- `available`：有供应商对该行程日的可信预报；condition、温度等字段可按实际数据填写；
- `unknown`：没有该日期的可信预报，可能是供应商没有返回、查询窗口不覆盖或结果被校验拒绝；不得填入推测天气或温度。

## P3 生成前天气上下文

P3 的 `query_weather_7d` 节点发生在 `generate_base_itinerary` 之前，输出独立的 `weather_context`。Planner 使用它判断室内/室外活动、时间段和备选方案，但不能把上下文当作可执行指令，也不能修改用户日期、预算或候选白名单。

生成后的 `apply_authoritative_weather` 节点再把同一批 Open-Meteo 记录按日期写入 `DayPlan.weather`，不会再次查询天气。模型生成的 weather condition、温度、source 只作为草稿，不具备事实权威；Critic 校验最终字段与同日证据一致。

天气查询不可用时仍可以生成基础行程，但必须把 `weather_status=degraded` 传给 Planner，使其采用不依赖具体天气事实的稳健安排，并在 trace 中记录脱敏的失败类别。P3 不因为未知天气自动修改已保存版本。

## 日期映射和 7 天覆盖范围

- 唯一映射键是 `DayPlan.date` 与天气记录的 ISO-8601 `date`，按日历日期相等匹配；
- 不按数组下标、星期字符串或供应商返回顺序映射；每个行程日最多绑定一条天气记录；
- 当前 `TripRequest` 允许 3 至 7 天，P3 天气节点覆盖请求的完整日期范围，最多 7 个日历日；
- Open-Meteo 接受 `start_date`、`end_date`，适配器一次请求覆盖最多 7 天；高德只用于把规范城市解析为坐标，不再提供天气事实；
- 供应商没有返回某个请求日期时，该日为 `unknown`，不能把相邻日期数据复制过去；
- `fetched_at` 是适配器取得 Open-Meteo 响应的 UTC 时间，不冒充供应商预报发布时间；旧行程可能为 `null`。

## 来源和配置

Open-Meteo 免费 API 用于本项目的非商业场景。页面标注并链接 [Open-Meteo](https://open-meteo.com/)；`weather.source` 为 `Open-Meteo`。天气预报接口不需要 API Key，默认地址为 `https://api.open-meteo.com/v1`。城市坐标仍通过高德地理编码取得，因此真实按城市查询需要 `AMAP_API_KEY`；旧 `WEATHER_API_KEY` 不再使用。城市解析或天气请求失败均按天气降级处理。

## 失败降级与建议边界

- 超时、配置错误、供应商错误、无效响应或部分覆盖不会伪造天气；可继续生成时返回 `null`/`unknown` 并记录降级；
- RAG 或模型提示词不能覆盖天气供应商事实；攻略中的“适合晴天”等描述只能作为非实时背景；
- 雨天建议仅提供轻量、可解释的准备提示（雨具、防滑等）；天气前置生成可以调整活动选择，但不自动删除或重排已经保存的行程；
- 天气驱动重规划另行执行：读取当前版本、生成差异预览、等待用户确认、重新校验后写入新版本。

## P3 验收用例

至少覆盖：

1. 3 天和 4 天请求按日期取得预报；
2. 7 天请求一次 Open-Meteo 日期范围调用覆盖全部日期；
3. 生成前证据和生成后权威回填具有相同来源与日期；
4. 7 天请求只有部分日期有预报，其余准确为 `unknown`；
5. 天气工具超时，Planner 收到降级状态且最终不包含伪造事实；
6. 模型试图输出与供应商不同的天气，权威回填和 Critic 拒绝冲突字段；
7. 不同日期顺序、重复记录和跨城市记录不会错误绑定。
