# 景点图片服务

行程生成完成后，后端只为 `poi_category = "spot"` 的活动获取图片。图片服务使用行程候选池中已经由高德核验的 `poi_id` 调用高德 POI 详情接口 `/v3/place/detail`，读取该 POI 的 `photos[].url`，并写入活动的 `image_url` 字段。

图片不会再根据景点名称调用通用图片搜索，也不会用城市图片或 Unsplash 图片替代高德 POI 图片。高德 POI 没有图片、图片接口失败或未配置高德密钥时，`image_url` 保持为 `null`，前端显示占位图。这样可以避免景点名称相似或城市热门景点导致的错配。

配置环境变量：

```dotenv
AMAP_API_KEY=your-amap-api-key
AMAP_BASE_URL=https://restapi.amap.com/v3
AMAP_TIMEOUT_SECONDS=10
AMAP_MAX_RETRIES=2
```

高德图片 URL 由高德返回，前端地点图片区域优先使用 `image_url`，缺少图片时展示本地占位图。
