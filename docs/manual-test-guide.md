# 觅旅完整手工测试流程

本文档用于验收当前项目的后端、前端、行程生成、持久化、版本、编辑、多轮会话、导出、故障降级和观测能力。

测试分为两部分：

1. **无密钥离线验收**：通过自动化替身测试完整链路，并手工验证健康检查、保存、版本、历史、导出和删除；无需 MoMA、高德或天气服务。
2. **真实服务联调**：手工验证生成、单日编辑、多轮会话、前端生成、地图和天气；这些操作会调用外部供应商，可能产生费用或受到限流。

后端统一使用端口 `8000`。

## 一、测试前准备

### 1. 检查分支和目录

```powershell
cd D:\Codes\Journey_Seeking
git branch --show-current
git status --short
```

### 2. 安装后端依赖

```powershell
python -m pip install -e ".[dev]"
python --version
```

要求 Python 3.11 或更高版本。

### 3. 配置文件

本地配置文件是 `backend/.env`。无密钥测试不需要真实密钥。真实联调至少需要：

```env
MOMA_API_URL=https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions
MOMA_MODEL=deepseek-v4-flash-0731
MOMA_API_KEY=你的MoMA密钥
MOMA_TIMEOUT_SECONDS=120
MOMA_MAX_RETRIES=0
MOMA_MAX_TOKENS=4096
ORCHESTRATION_STEP_TIMEOUT_SECONDS=0
AMAP_API_KEY=你的高德服务密钥
WEATHER_API_KEY=你的天气密钥
```

不要把 `backend/.env` 提交到 Git，也不要把 API Key 写入日志、截图或测试报告。

### 4. Windows PowerShell 中文显示

Windows PowerShell 5.1 可能在发送请求体时就把中文编码成问号；仅调整输出编码无法修复已写入数据库的 `?`。先执行：

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
```

提交 JSON 时统一使用 UTF-8 字节数组：

```powershell
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($trip)
```

如果仍显示异常，先检查提交前的 `$trip`；再重新创建一条行程。把结果保存为 UTF-8 文件，用 VS Code 打开确认实际内容：

```powershell
$created | ConvertTo-Json -Depth 20 | Out-File .\created-trip.json -Encoding utf8
```

## 二、自动化基线

手工测试前先确认自动化基线：

```powershell
cd D:\Codes\Journey_Seeking
python -m pytest -q
python -m pytest backend/tests/e2e -q
python -m ruff check .
python -m ruff format --check .
```

构建前端：

```powershell
cd frontend
npm ci
npm run build
cd ..
```

测试结果应记录在验收表中。Vite 关于 chunk 大小的提示不是构建失败。

## 三、启动后端和健康检查

在一个 PowerShell 窗口启动后端：

```powershell
cd D:\Codes\Journey_Seeking
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

保持该窗口运行。在另一个窗口执行：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health -Method Get
```

预期：

```json
{"status":"ok"}
```

打开 OpenAPI：

```text
http://127.0.0.1:8000/docs
```

确认能看到生成、保存、历史、编辑、会话、导出、删除和聊天接口。

如果出现 `Unable to connect to the remote server`，先检查服务是否启动：

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

## 四、无密钥离线验收

### 1. 准备人工行程请求

```powershell
$trip = @{
  itinerary = @{
    destination = "杭州"
    start_date = "2026-10-01"
    end_date = "2026-10-03"
    summary = "杭州三日游手工验收"
    days = @(
      @{
        date = "2026-10-01"
        title = "西湖与文化"
        activities = @(
          @{ time = "09:00"; name = "西湖"; description = "环湖游览"; location = "西湖"; estimated_cost = 0 },
          @{ time = "14:00"; name = "灵隐寺"; description = "文化参观"; location = "灵隐寺"; estimated_cost = 30 }
        )
      },
      @{
        date = "2026-10-02"
        title = "城市漫步"
        activities = @(
          @{ time = "10:00"; name = "河坊街"; description = "历史街区漫步"; location = "河坊街"; estimated_cost = 0 }
        )
      },
      @{
        date = "2026-10-03"
        title = "返程"
        activities = @()
      }
    )
    total_estimated_cost = 30
  }
  expected_version = $null
} | ConvertTo-Json -Depth 20
```

### 2. 创建并保存行程

```powershell
$created = Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/trip/save `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($trip))

$created | ConvertTo-Json -Depth 20
$tripId = $created.trip_id
$version = $created.version
```

预期：HTTP 200，`trip_id` 非空，`version=1`。确认中文字段正常保存。

### 3. 查询列表、当前版本和版本列表

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/trip?limit=20" | ConvertTo-Json -Depth 20
Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId" | ConvertTo-Json -Depth 20
Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/versions" | ConvertTo-Json -Depth 20
Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/versions/1" | ConvertTo-Json -Depth 20
```

确认列表包含行程，当前版本是 1，历史版本 1 可读取，日期和费用没有变化。

### 4. 保存版本 2 和验证版本冲突

```powershell
$update = @{
  itinerary = @{
    trip_id = $created.trip_id
    version = 1
    destination = $created.destination
    start_date = $created.start_date
    end_date = $created.end_date
    summary = "杭州三日游版本二"
    days = $created.days
    total_estimated_cost = $created.total_estimated_cost
  }
  expected_version = 1
} | ConvertTo-Json -Depth 20

$updated = Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/trip/save `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($update))
$updated.version
```

预期版本变为 2。再次提交同一个 `$update`，预期 HTTP 409：

```json
{"code":"TRIP_VERSION_CONFLICT","request_id":"req_..."}
```

确认旧版本没有覆盖版本 2。

### 5. 查看并恢复历史版本

```powershell
$versions = Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/versions"
$versions | ConvertTo-Json -Depth 20

# 查看指定历史版本
$old = Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/versions/1"
$old | ConvertTo-Json -Depth 20

# 将版本 1 恢复为新版本；不会删除版本 1、2 等历史记录
$restoreBody = @{ version = 1; expected_version = [int]$versions.current_version } | ConvertTo-Json
$restored = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/trip/$tripId/restore" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($restoreBody))
$restored.version
```

预期恢复请求返回新版本号（例如当前版本 2 恢复版本 1 后生成版本 3）。前端结果页的“版本历史”抽屉提供同样的“查看”和“恢复”操作；恢复后旧编辑会话需要重新开启。

### 5. 导出 Markdown 和 PDF

```powershell
Invoke-WebRequest "http://127.0.0.1:8000/api/trip/$tripId/export?format=markdown" -OutFile .\trip-current.md
Invoke-WebRequest "http://127.0.0.1:8000/api/trip/$tripId/export?format=pdf" -OutFile .\trip-current.pdf
```

检查 Markdown 中文、日期、活动、费用、天气和 POI 状态。确认不包含 `None`、Prompt、Key、traceback 或内部路径。

检查 PDF：

```powershell
$bytes = [System.IO.File]::ReadAllBytes(".\trip-current.pdf")
[System.Text.Encoding]::ASCII.GetString($bytes[0..3])
```

预期输出 `%PDF`。打开 PDF，确认中文字体、换行、空活动日和分页正常。使用 `?version=1&format=markdown` 导出历史版本，确认内容是版本 1 而不是当前版本。

### 6. 重启恢复

在 uvicorn 窗口按 `Ctrl+C`，然后重新执行：

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

在另一个窗口执行：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId" | ConvertTo-Json -Depth 20
```

确认 SQLite 中的行程和版本 1、2 仍可读取。

### 7. 删除和 404 验证

```powershell
Invoke-WebRequest "http://127.0.0.1:8000/api/trip/$tripId" -Method Delete
```

再次读取当前行程、历史版本和导出接口，均应返回 HTTP 404 `TRIP_NOT_FOUND`。

### 8. 无密钥完整链路

手工调用编辑接口仍会请求 MoMA，因此无密钥环境下使用自动化替身测试覆盖完整链路：

```powershell
python -m pytest backend/tests/e2e -q
```

该测试执行生成、保存、会话两轮编辑、历史版本、Markdown/PDF 导出和删除，并验证超时及编排失败。它使用临时 SQLite，不访问真实供应商。

## 五、真实编辑与多轮会话

以下步骤需要配置有效 `MOMA_API_KEY`。请先按“真实服务联调”章节配置密钥并重启后端，再创建一条新的人工行程，确保 `$tripId` 指向未删除的行程。

### 1. 单日编辑

```powershell
$edit = @{ expected_version = 2; date = "2026-10-02"; instruction = "减少当天活动，保留轻松的城市漫步" } | ConvertTo-Json
$editResult = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/trip/$tripId/edit" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($edit))
$editResult | ConvertTo-Json -Depth 20
```

预期版本变为 3，只有 `2026-10-02` 变化，并返回 `change_summary`。使用不在行程内的日期，预期 HTTP 422 `INVALID_TRIP_REQUEST`。

### 2. 多轮会话编辑

创建会话：

```powershell
$sessionBody = @{ version = 3; constraints = @{ budget = 500; preferences = @("文化", "休闲"); pace = "relaxed" } } | ConvertTo-Json -Depth 10
$session = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/trip/$tripId/sessions" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($sessionBody))
$sessionId = $session.session_id
```

执行两轮不同日期编辑：

```powershell
$body1 = @{ date = "2026-10-01"; instruction = "减少景点数量，保留文化体验" } | ConvertTo-Json
$result1 = Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/sessions/$sessionId/edit" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body1))

$body2 = @{ date = "2026-10-02"; instruction = "安排节奏轻松的活动，不超过预算" } | ConvertTo-Json
$result2 = Invoke-RestMethod "http://127.0.0.1:8000/api/trip/$tripId/sessions/$sessionId/edit" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body2))
```

确认版本连续递增、`recent_turns` 保留两轮、预算和日期约束仍然存在。删除会话：

```powershell
Invoke-WebRequest "http://127.0.0.1:8000/api/trip/$tripId/sessions/$sessionId" -Method Delete
```

再次读取该会话应返回 HTTP 404 `SESSION_NOT_FOUND`。

## 六、错误响应和请求观测

### 1. 请求 ID

```powershell
$response = Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/health `
  -Headers @{ "X-Request-ID" = "manual-health-001" }

$response.Headers["X-Request-ID"]
```

预期响应头仍为 `manual-health-001`。错误响应 JSON 也应包含 `request_id`。

### 2. 无效请求

向 `/api/trip/generate` 发送空目的地或少于 3 天的日期，预期 HTTP 422、`INVALID_TRIP_REQUEST`。

### 3. 日志检查

生成请求成功时，后端日志应包含：

```text
orchestration_completed
request_completed
```

编排轨迹应包含城市解析、知识检索、生成、候选质量、地图、天气、图片和 Critic。失败时检查：

```text
trip_service_failed request_id=req_... code=MOMA_TIMEOUT
orchestration_failed request_id=req_... code=CRITIC_REJECTED findings=...
```

日志不得包含 API Key、完整 Prompt、Authorization Header、供应商原始响应或 traceback。

## 七、前端手工验收

启动前端：

```powershell
cd D:\Codes\Journey_Seeking\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

访问：

```text
http://127.0.0.1:5173
```

### 1. 生成流程

填写杭州、2026-10-01 至 2026-10-03、人数 1、预算 1500、轻松节奏和文化/美食偏好，点击开始规划。确认 loading、进度条、成功跳转和失败提示正常。

### 2. 结果页

依次检查概览、预算、地图、天气、智能调整、地点图片和每日行程。地图 Key 缺失或图片加载失败时不应白屏；天气未知时应明确显示未知状态。

### 3. 保存、历史和编辑

点击保存，刷新或打开历史，确认可重新打开行程。选择某天执行两轮编辑，确认版本递增、只影响目标日期、显示修改摘要，失败不覆盖旧版本。

### 4. 导出和移动端

下载 Markdown/PDF，确认文件内容正确。使用浏览器 DevTools 的 375px 和 390px 移动视口检查表单、地图、每日活动、按钮和历史抽屉无横向溢出或遮挡。

## 八、真实服务联调

### 1. 检查 MoMA 地址

不携带密钥检查地址：

```powershell
$url = "https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions"
try { Invoke-WebRequest -Uri $url -Method Head -TimeoutSec 15 } catch { $_.Exception.Message }
```

返回 `401 Unauthorized` 通常表示网络和服务地址可达，认证检查正常。

### 2. 真实生成

配置真实 Key 后重启后端，使用 OpenAPI 或前端生成三日杭州行程。选择未来 1 至 3 天内的日期，以便同时验证天气预报；过期日期只能验证生成结构，无法验证真实天气。通过 PowerShell 或浏览器开发工具设置请求头：

```text
X-Request-ID: manual-moma-001
```

确认 HTTP 200、日期连续、预算合法、POI/路线/天气状态真实可解释，并在日志中记录请求 ID、总耗时、步骤状态、POI 核实率和路线核实率。

### 3. MoMA 超时故障

临时设置：

```env
MOMA_TIMEOUT_SECONDS=5
MOMA_MAX_RETRIES=0
```

重启后再次生成，预期 HTTP 504、`MOMA_TIMEOUT`，且不会创建行程。测试结束恢复正常配置。

### 4. 地图和天气降级

临时移除或填写无效的 `AMAP_API_KEY`、`WEATHER_API_KEY` 后重启并生成。基础行程应尽量保留；地图状态应为 `partial` 或 `unavailable`，天气应为空或 `unknown`，不得伪造已核实数据。

### 5. Critic 拒绝

如果真实生成返回 HTTP 502 `CRITIC_REJECTED`，查看日志中的 `findings`。常见规则包括预算超限、日期不一致、POI 来源无效、路线来源无效或未知天气包含事实。确认响应没有泄露 Prompt 或供应商原始响应。

### 6. 502 定位

仅凭 uvicorn 的访问行 `POST /api/trip/generate ... 502` 不能判断原因。必须查看同一请求前面的结构化日志：

```text
trip_service_failed request_id=req_... code=MOMA_INVALID_RESPONSE
moma_provider_failed request_id=req_... error_type=MomaRateLimitError
orchestration_failed request_id=req_... code=CRITIC_REJECTED findings=...
```

按分类处理：

| 日志 | 含义 | 检查方向 |
| --- | --- | --- |
| `MOMA_INVALID_RESPONSE` | 上游返回内容不是可用的行程 JSON | 检查模型、Prompt 兼容性和 `MOMA_MAX_TOKENS` |
| `ITINERARY_VALIDATION_ERROR` | JSON 存在但不符合日期、费用或结构契约 | 查看生成请求和模型输出对应的结构字段 |
| `moma_provider_failed ... MomaRateLimitError` | 上游限流 | 降低请求频率，确认额度和重试策略 |
| `moma_provider_failed ... MomaAuthenticationError` | Key 或权限错误 | 检查 Key、模型权限和服务地址 |
| `moma_provider_failed ... MomaServiceError` | 上游返回服务错误或网络错误 | 检查上游状态、地址和请求预算 |
| `orchestration_failed ... CRITIC_REJECTED` | 行程完成补全但未通过规则校验 | 查看 `findings` 中的规则和路径 |

每次真实联调都应记录响应中的 `request_id`，并用它关联 `trip_service_failed`、`moma_provider_failed`、`orchestration_failed` 和 `request_completed` 日志。不要记录 API Key、完整 Prompt 或供应商原始响应。

## 九、部署、备份和回滚检查

备份 SQLite 文件：

```powershell
Copy-Item backend/data/trips.sqlite3 backend/data/trips.sqlite3.backup
```

部署前运行：

```powershell
python -m pytest -q
cd frontend
npm ci
npm run build
```

回滚应用代码时保留 SQLite 文件，不要删除行程数据库。回滚后重新启动端口 `8000`，读取一个已有 `trip_id` 和历史版本，确认数据仍然可用。

## 十、验收记录模板

### 2026-10-12 自动化辅助验收结果

桌面和移动端浏览器检查已由 Chrome DevTools 脚本执行：1440x900 和 390x844 均无横向溢出，结果页、地点图片区和每日行程交互可用。空表单显示校验错误和提示消息。离线端到端与回归测试共 228 项通过，前端构建通过。

真实服务第一次尝试在 `MOMA_MAX_RETRIES=1` 时耗时 505.31 秒后于 `generation` 阶段返回 `MomaServiceError`，未进入智能调整；该失败记录仍保留用于稳定性观察。随后将 `MOMA_MAX_RETRIES=0` 后重试成功：生成耗时 167.30 秒，智能调整耗时 130.72 秒；生成/调整 total tokens 分别为 13,018 / 10,422，POI 核实率 12/12，路线核实率 9/9，非目标日期和历史版本保持不变，Markdown/PDF 导出成功。

| 项目 | 结果 | 备注 |
| --- | --- | --- |
| `/health` | 通过/失败 | |
| OpenAPI | 通过/失败 | |
| 后端测试 | 通过/失败 | |
| 前端构建 | 通过/失败 | |
| 无密钥保存/版本 | 通过/失败 | |
| 单日编辑 | 通过/失败 | |
| 多轮会话 | 通过/失败 | |
| Markdown 导出 | 通过/失败 | |
| PDF 导出 | 通过/失败 | |
| 重启恢复 | 通过/失败 | |
| 请求 ID | 通过/失败 | |
| 真实 MoMA 生成 | 通过/失败 | 请求 ID： |
| POI/路线补全 | 通过/失败 | 核实率： |
| 天气补全 | 通过/失败 | |
| 外部服务降级 | 通过/失败 | |
| 前端桌面流程 | 通过/失败 | |
| 前端移动端流程 | 通过/失败 | |
| 删除和 404 | 通过/失败 | |
| 备份/回滚 | 通过/失败 | |
