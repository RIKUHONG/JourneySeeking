# 后续迭代路线图：POI、缓存与天气

本文将“提高 POI 命中率和缓存”与“天气预报和行程建议”拆成有依赖关系的阶段，作为当前迭代的执行基线。

## 决策

优先顺序为：

1. 建立 POI/路线质量基线并提高 POI 命中率。
2. 增加可替换的缓存抽象，先使用内存实现验证，再按实际规模接入 Redis。
3. 接入按日期的天气预报和轻量建议。
4. 将自动替换活动、重排路线作为后续 P2 设计，不纳入天气第一版。

原因是 POI 坐标是路线规划和行程可执行性的前置条件；当前天气客户端已有适配器和 mock，但尚未接入 `TripService` 主链路。

## P1-1 分支

POI 命中率基线与匹配优化在独立分支 `feature/poi-quality` 进行。该分支必须从最新 `main` 创建，不直接向 `main` 提交；完成后通过 PR 合并。建议创建命令：

```powershell
git checkout main
git pull --ff-only origin main
git checkout -b feature/poi-quality
```

该分支只包含 POI 匹配、质量指标、相关日志和离线测试，不提前引入天气字段或 Redis 运行时依赖。

## 分工

### 成员 C：P1 后续工作的唯一负责人

- 独立负责 P1-1、P1-2 和 P1-3 的需求拆解、实现、文档、测试和 PR 提交。
- 负责 POI 统计是否进入公开 API、天气字段契约、日期映射和兼容行为；先更新 `docs/api-contract.md` 再实现。
- 负责 Pydantic 模型、API 回归测试、缓存故障降级和地图/天气失败时的基础行程保留。
- 负责 POI、缓存、天气三个阶段之间的依赖协调，不在前一阶段未达到门槛时启动后一阶段。

- P1 阶段不再拆分给成员 A 或 B；A、B 不承担这些阶段的实现、审核或测试工作。
- POI 匹配采用分层策略：标准化完全匹配、后缀归一化、唯一候选确认；多候选必须保留 `ambiguous`，不得凭相似度猜测。
- 缓存先实现接口和内存版本，再按多实例或调用量需求实现 Redis；Redis 不得成为启动硬依赖。
- 天气第一版只提供按日期预报和可解释的雨天/未知天气建议，不自动替换或重排行程。

## 阶段和门槛

| 阶段 | 主责 | 主要交付 | 完成门槛 |
| --- | --- | --- | --- |
| P1-1 POI 基线与匹配 | C | 分支 `feature/poi-quality`；`poi_verified_rate`、`poi_not_found_rate`、`poi_ambiguous_rate`、`route_verified_rate`；匹配逻辑和测试 | 不误把模糊候选标为 verified；ID/坐标来自供应商结果 |
| P1-2 缓存抽象 | C | 分支 `feature/map-cache`；POI/路线 cache interface、key、TTL、内存实现 | 命中/未命中及缓存故障降级测试通过 |
| P1-3 天气展示 | C | 分支 `feature/weather-trip-advice`；`DayPlan` 可选天气字段、日期映射、轻量建议 | 3～4 天可覆盖；5～7 天超范围为 unknown；天气失败保留基础行程 |
| P2-1 Redis | C | 分支 `feature/redis-cache`；Redis adapter、连接配置、序列化、降级 | 有多实例或调用量依据；内存实现仍可运行 |
| P2-2 自动调度 | C | 分支 `feature/weather-auto-scheduling`；替代活动、重排路线、用户确认 | 单独评审，不随天气第一版合入 |

## 协作顺序

每一阶段均由成员 C 独立完成需求确认、契约更新、业务实现、测试和验收记录。各分支从合并后的最新 `main` 创建，按 P1-1 → P1-2 → P1-3 顺序推进；P2-1 Redis 在缓存抽象稳定且有部署依据后再单独启动。
