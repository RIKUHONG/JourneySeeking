# 觅旅协作规范

## 1. 分支策略

- `main`：可发布、可部署的稳定分支。
- `feature/<主题>`：新功能，例如 `feature/trip-models`。
- `fix/<主题>`：缺陷修复，例如 `fix/moma-invalid-json`。
- `docs/<主题>`：文档变更。

禁止直接向 `main` 推送。所有变更通过 Pull Request 合并，并至少由另一位成员完成一次 review。

## 2. 开发流程

```text
同步 main → 创建短生命周期分支 → 编写代码和测试 → 本地检查 → 推送分支 → Pull Request → review → 合并
```

开始工作前：

```powershell
git checkout main
git pull --ff-only origin main
git checkout -b feature/<topic>
```

提交前至少运行与改动相关的测试；如果项目已配置 lint/format，也必须执行对应检查。

## 3. 提交信息

使用 Conventional Commits 风格：

- `feat:` 新功能
- `fix:` 缺陷修复
- `test:` 测试
- `refactor:` 重构
- `docs:` 文档
- `chore:` 工具或依赖维护

示例：

```text
feat: add itinerary request and response schemas
fix: handle malformed MoMA response
test: add trip generation API cases
```

## 4. Pull Request 规范

PR 描述必须说明：

1. 变更目的和范围；
2. 关联的 Issue；
3. 如何验证；
4. 是否改变 API 契约、环境变量或数据库结构；
5. 是否需要部署配置变更。

PR 应保持单一主题，避免把大规模格式化、重命名和业务修改混在一起。

## 5. 代码与安全约定

- 不提交 `.env`、API Key、Token、真实用户数据和本地数据库。
- 只提交 `.env.example`，其中只能放变量名和示例值。
- 不把本地参考项目 `repo_inspect_20260923/` 拷贝进仓库。
- 路由层不直接调用 MoMA、高德或天气服务，统一通过 service/integration 层调用。
- 外部服务必须设置超时，并提供可测试的 mock。
- API 响应结构和错误码以 `docs/api-contract.md` 为准。

## 6. Review 检查清单

- 是否有对应测试？
- 是否保持向后兼容？
- 是否泄露密钥或本地路径？
- 是否处理超时、空响应和非法 JSON？
- 是否更新相关文档？
- 是否引入不必要的依赖或耦合？

## 7. 冲突处理

接口字段或业务含义发生冲突时，先更新 `docs/api-contract.md`，再修改实现。不要通过各自分支“猜测”字段含义。无法达成一致时，由项目负责人根据兼容性和测试成本做最终决定。
