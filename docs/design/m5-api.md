# M5 API 契约：update / sync_pending 工作流端点

> 日期：2026-09-22 · 状态：设计定稿（评审用，未改任何代码）
> 作者：api-designer（刘数面） · 底稿：m5-architecture.md §6 + §1/§4/§8
> 交付对象：backend-engineer（凭本文可直接写 Pydantic，无需追问）
> 范围：**2 个新端点 + 3 个增强端点**；3 个 legacy 端点仅记录现状（冻结，见 §7）

---

## 0. 端点总清单

| # | 方法 | 路径 | 类型 | 请求 | 响应 |
|---|---|---|---|---|---|
| 1 | POST | `/articles/{aid}/update/workflow` | **新增** | `WorkflowUpdateIn` | `WorkflowStartOut` / 错误 |
| 2 | POST | `/sync/pending/workflow` | **新增** | `WorkflowSyncIn` | `SyncStartOut` / 错误 |
| 3 | GET | `/runs` | **增强** | query: `limit`, `kind?`, `article_id?` | `RunListItem[]`（每项**新增** `kind`） |
| 4 | GET | `/runs/{run_id}` | **增强** | path: `run_id` | `RunDetail`（**新增** `kind`） |
| 5 | POST | `/runs/{run_id}/resume` | **零变化** | `ResumeIn` | `ResumeOut` / 409 |

---

## 1. 通用约定（所有端点适用）

1. **错误体结构统一**：`{"detail": "<人类可读字符串>"}`，与 `server/api.py` 现状完全一致（`HTTPException(status, msg)` 产出形态）。前端 `api.js` 拦截器读 `err.response.data.detail`，**禁止改成结构化错误对象**。
2. **两类 422 并存**（实现与消费方都要区分）：
   - **业务 422**：`HTTPException(422, "<字符串>")` → `{"detail": "没有已发布实例可更新，先 publish"}`（detail 是**字符串**）；
   - **请求校验 422**：FastAPI/Pydantic 自动产出 → `{"detail": [{loc, msg, type, ...}]}`（detail 是**数组**）。
   两者 HTTP 码相同，形状不同；判 `typeof detail === 'string'` 即可分流（`api.js` 现状 `JSON.stringify` 兜底已兼容）。
3. **鉴权**：沿用全局中间件——配了 `api_token` 时非信任来源须带 `X-API-Token`，否则 401 `{"detail": "无效的 API Token"}`。本文各端点不再重复列 401。
4. **版本**：无 URL 版本号；本组端点以 `Workflow*` Pydantic 模型 + `/workflow` 后缀与 legacy 区分，破坏性变更须新路径而非改语义（向后兼容优先）。
5. **run 状态枚举**（契约字段，逐字）：`running | waiting_human | done | failed`。
6. **kind 枚举**（契约字段，逐字）：`publish | update`；**存量行缺省 `publish`**（`ALTER TABLE ... kind TEXT NOT NULL DEFAULT 'publish'`，老数据读出即 publish，前端/MCP 无需迁移）。
7. **run_id 格式**：`uuid.uuid4().hex[:12]`，12 位小写十六进制字符串。
8. **同步等待 vs 立即返回的语义分界**（本组端点核心规则）：

| 端点类别 | 语义 | 客户端动作 |
|---|---|---|
| legacy `/articles/{aid}/update`、`/sync/pending` | **同步等待**：HTTP 阻塞到全部平台更新完才返回（分钟级，有超时风险） | 拿到的已是终态结果 |
| 新 `/articles/{aid}/update/workflow`、`/sync/pending/workflow` | **立即返回 run_id**：同步段只做预检 + 建 run（毫秒级），后台线程跑图 | 轮询 `GET /runs/{run_id}` 至 `done/failed/waiting_human`；挂起时 `POST /runs/{run_id}/resume` |
| MCP 工具（§6.4 切流） | 工具内部代为轮询至终态（deadline **900s**），对 agent 仍是"同步返回结果" | agent 无感，与 HTTP 异步契约解耦 |

---

## 2. 端点 1：POST `/articles/{aid}/update/workflow`（新增）

启动一篇原地更新工作流（`kind='update'` 图），**立即返回 run_id**。

### 2.1 路径参数

| 字段 | 类型 | 必填 | 默认 | 示例 | 说明 |
|---|---|---|---|---|---|
| `aid` | integer | 是 | — | `3` | 文章 ID；非整数 → 请求校验 422 |

### 2.2 请求体 `WorkflowUpdateIn`

| 字段 | 类型 | 必填 | 默认值 | 示例 JSON | 校验规则 |
|---|---|---|---|---|---|
| `platforms` | `array<string>` 或 `null` | 否 | `null` | `["csdn","zhihu"]` | `null`/缺省/`[]` **三者等价 = 全部可更新实例**（与 legacy `if platforms:` 真值过滤一致，见 §5-B1）；元素为平台 ID 字符串 |
| `account` | string | 否 | `"default"` | `"default"` | 账号键，空串按默认处理 |
| `dry_run` | boolean | 否 | `false` | `true` | `true` = 预演：不触真实平台、跳过门禁、合成结果（ADR-005） |

**无 `draft_only` 字段**——update 无草稿概念（与 `WorkflowPublishIn` 的差异，勿照抄）。

请求示例：
```json
{ "platforms": ["csdn", "zhihu"], "account": "default", "dry_run": false }
```
最小请求（全部可更新实例）：`{}`

### 2.3 成功响应 200 `WorkflowStartOut`

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| `run_id` | string(12) | 是 | `"a1b2c3d4e5f6"` | 工作流 run 标识 |
| `status` | string 枚举 | 是 | `"running"` | 恒为 `"running"`（刚启动） |
| `poll` | string | 是 | `"/runs/a1b2c3d4e5f6"` | 轮询路径 |

```json
{ "run_id": "a1b2c3d4e5f6", "status": "running", "poll": "/runs/a1b2c3d4e5f6" }
```

### 2.4 错误（detail 均为字符串）

| 码 | detail 示例 | 触发条件 |
|---|---|---|
| 409 | `工作流引擎已通过 config workflow.enabled=false 禁用` | `_workflow_enabled()` 为假；**先于**一切预检判断 |
| 404 | `文章 3 不存在` | `hub.get(aid)` 为空（runner.start 同步预检） |
| 422 | `没有已发布实例可更新，先 publish` | 目标实例集为空：`get_publications ∩ platforms ∩ (post_id or edit_url)` 为 `[]`；**未建 run** |

**错误映射实现要点**：`runner.start(kind='update')` 抛的 `ValueError` 按文案分流——含 `不存在` → 404，含 `没有已发布实例` → 422，其余启动期 `ValueError`（不应出现，防御性）→ 422。**不可照抄 publish/workflow 的"全部 ValueError → 404"**，否则无目标实例会被误报为文章不存在。

---

## 3. 端点 2：POST `/sync/pending/workflow`（新增）

发现全部 pending 实例，按文章分组，**一文一 run** 扇出启动（编排层，不建独立图，ADR-008），立即返回全部 run_id。

### 3.1 请求体 `WorkflowSyncIn`（body 可整体省略）

| 字段 | 类型 | 必填 | 默认值 | 示例 JSON | 校验规则 |
|---|---|---|---|---|---|
| `account` | string | 否 | `"default"` | `"default"` | 透传给每篇 runner.start |
| `dry_run` | boolean | 否 | `false` | `true` | 透传；冒烟用 |

请求示例：`{ "account": "default", "dry_run": true }`；或不带 body（全默认）。实现提示：FastAPI 参数写 `body: WorkflowSyncIn = WorkflowSyncIn()` 使 body 可省略。

### 3.2 成功响应 200 `SyncStartOut`

| 字段 | 类型 | 必填 | 示例 | 语义 |
|---|---|---|---|---|
| `count` | integer ≥ 0 | 是 | `2` | **成功启动**的 run 数；`count=0` **不是错误**（无 pending 或全部启动失败，看 `failed`） |
| `runs` | array | 是 | 见下 | 成功启动清单，按发现顺序 |
| `runs[].article_id` | integer | 是 | `3` | 文章 ID |
| `runs[].title` | string | 是 | `"深入 LangGraph"` | 文章标题（来自 pending 发现 SQL） |
| `runs[].run_id` | string(12) | 是 | `"a1b2c3d4e5f6"` | 该篇 update run |
| `failed` | array | 是（可为空 `[]`） | 见下 | **启动失败清单**（§6-D 决策新增，底稿未定义部分失败；静默丢弃会让调用方把"全失败"误读成"无 pending"） |
| `failed[].article_id` | integer | 是 | `7` | 启动失败的文章 ID |
| `failed[].title` | string | 是 | `"另一篇"` | 文章标题 |
| `failed[].reason` | string | 是 | `"文章 7 不存在"` | 该篇 `runner.start` 抛出的错误文案 |

```json
{
  "count": 2,
  "runs": [
    { "article_id": 3, "title": "深入 LangGraph", "run_id": "a1b2c3d4e5f6" },
    { "article_id": 7, "title": "另一篇", "run_id": "b2c3d4e5f6a1" }
  ],
  "failed": []
}
```

无待同步（或全部启动失败）：
```json
{ "count": 0, "runs": [], "failed": [ { "article_id": 7, "title": "另一篇", "reason": "没有已发布实例可更新，先 publish" } ] }
```

### 3.3 错误

| 码 | detail 示例 | 触发条件 |
|---|---|---|
| 409 | `工作流引擎已通过 config workflow.enabled=false 禁用` | 引擎禁用，**未启动任何 run** |
| —（无 404/422） | — | 单篇的"文章不存在/无目标"**不升级为全局 HTTP 错误**，进 `failed[]`（失败按篇隔离是 ADR-008 收益，见 §5-B4） |

### 3.4 扇出时序（同步段毫秒级）

```
→ get_pending_updates() 按 article_id 分组（与 legacy 同一段 SQL）
→ 每组 runner.start(kind='update', platforms=组内平台集)   # ValueError → failed[]，继续下一篇
→ 返回 {count, runs, failed}
后台：各 run 独立线程推进；同平台跨 run 由 per-key 互斥串行，POOL_MAX=4
```

---

## 4. 端点 3–5：/runs 系列（增强 / 零变化）

### 4.1 GET `/runs`（增强：新增 2 个可选 query + 响应项新增 `kind`）

**Query 参数：**

| 字段 | 类型 | 必填 | 默认 | 示例 | 校验 |
|---|---|---|---|---|---|
| `limit` | integer | 否 | `50` | `100` | 沿用现状，无边界校验（不新增约束） |
| `kind` | string 枚举 `publish\|update` | 否 | 不过滤 | `update` | 缺省 = **返回全部 kind**（老客户端无感）；非法值 → 请求校验 422 |
| `article_id` | integer | 否 | 不过滤 | `3` | 与 `kind` 可组合（AND）；非法类型 → 请求校验 422 |

**响应 200：`RunListItem[]`**（`created_at DESC` 排序不变）

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| `id` | string(12) | 是 | `"a1b2c3d4e5f6"` | run_id |
| `article_id` | integer | 是 | `3` | 文章 ID |
| `title` | string | 是 | `"深入 LangGraph"` | 启动时快照 |
| `platforms` | array<string> | 是 | `["csdn","zhihu"]` | 启动时目标平台 |
| `status` | string 枚举 | 是 | `"waiting_human"` | `running\|waiting_human\|done\|failed` |
| `error` | string | 是（可 `""`） | `""` | 终态错误摘要 |
| `dry_run` | integer `0\|1` | 是 | `0` | **历史返回数字非布尔**，等价布尔；勿改 `true/false`（兼容性，§6-A） |
| `kind` | string 枚举 | 是 | `"update"` | **本次新增**；存量行 `"publish"` |
| `human_task` | object 或 null | 是 | `{"platform":"juejin","message":"...","edit_url":"..."}` | 仅 `waiting_human` 非 null |
| `summary` | object 或 null | 是 | `{"targets_total":2,"targets_ok":2,"ok":true}` | update 图 summary 无 `pending_human` 列 |
| `created_at` | number(float 秒) | 是 | `1758547200.12` | |
| `updated_at` | number(float 秒) | 是 | `1758547260.45` | |

列表项**不含** `results/decisions` 明细（沿用现状，明细走 GET detail）。

### 4.2 GET `/runs/{run_id}`（增强：响应新增 `kind`）

**响应 200 `RunDetail`** = 列表字段全集，**去掉** `human_task/summary` 顶层字段，**加上**：

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| `kind` | string 枚举 | 是 | `"update"` | **本次新增** |
| `result` | object | 是 | `{"results":[...],"decisions":[...],"summary":{...},"human_task":null}` | 由 `result_json` 解析 |
| `result.results` | array | 是 | `[{"platform":"csdn","ok":true}]` | 每平台终态 `{platform, ok, status?, error?, attempts?, note?}` |
| `result.decisions` | array | 是 | `[{"platform":"csdn","error":"...","attempts":1,"action":"retry","reason":"...","by":"heuristic","ts":...}]` | 分诊留痕 |
| `checkpoint` | object | 是 | `{"node":"update_instance","current_platform":"csdn","attempts":1,"queue_left":1}` | 实时进度；`node` 对 update run 可能出现 `next_target`/`update_instance` 等**新节点名**——前端按字符串展示，无需改动 |
| `checkpoint.node` | string | 是 | `"triage"` | 下一个待执行节点；`""` = 已终态 |
| `checkpoint.current_platform` | string | 是 | `"csdn"` | 当前平台（`""` = 队列空） |
| `checkpoint.attempts` | integer | 是 | `1` | 当前平台已尝试次数 |
| `checkpoint.queue_left` | integer | 是 | `1` | 剩余平台数 |

**404**：`{"detail": "run 不存在"}`（现状不变；对 update/publish 两种 kind 一致）。

### 4.3 POST `/runs/{run_id}/resume`（**契约零变化**）

请求 `ResumeIn`：

| 字段 | 类型 | 必填 | 默认 | 示例 |
|---|---|---|---|---|
| `approved` | boolean | 否 | `true` | `true` |
| `note` | string | 否 | `""` | `"掘金侧已手动点发布"` |

```json
{ "approved": true, "note": "" }
```

响应 200 `ResumeOut`：

| 字段 | 类型 | 必填 | 示例 |
|---|---|---|---|
| `run_id` | string(12) | 是 | `"a1b2c3d4e5f6"` |
| `status` | string 枚举 | 是 | `"running"` |

```json
{ "run_id": "a1b2c3d4e5f6", "status": "running" }
```

**409（全部 detail 字符串，现状沿用）**：`run {id} 不存在` / `run {id} 状态为 done，仅 waiting_human 可恢复` / `run 正在执行中，稍后再试`。
注：run 不存在在 resume 上返 **409**（api.py 现状把一切 `ValueError` 映 409），而 GET detail 返 404——**这是现状怪癖，本阶段如实冻结，不"顺手修正"**。
**行为增强（对调用方不可见）**：服务端按 meta 行 `kind` 路由到对应图恢复；请求/响应 schema 逐字不变。

---

## 5. 校验与边界规则总表

| # | 场景 | 端点 | 行为 | HTTP |
|---|---|---|---|---|
| B1 | `platforms: []`（显式空数组） | update/workflow | **等同 `null` = 全部可更新实例**（legacy `if platforms:` 真值语义逐字对齐；拒绝 `[]` 会造成 legacy 客户端行为倒退） | 200 |
| B2 | `platforms` 含未发布/未知平台 | update/workflow | 交集过滤后仅剩合法目标；**全被滤掉 → 422**，部分被滤掉 → 只更新交集（legacy 同语义） | 200 / 422 |
| B3 | 文章不存在 | update/workflow | 启动预检拒绝，**未建 run** | 404 |
| B4 | 单篇启动失败（不存在/无目标） | sync/workflow | 进 `failed[]`，其余篇照常启动，**不中断、不升级全局错误** | 200 |
| B5 | 引擎禁用 `workflow.enabled=false` | update/workflow、sync/workflow | 未建任何 run；先于一切预检 | 409 |
| B6 | 无目标发布实例 | update/workflow | `get_publications ∩ platforms ∩ (post_id or edit_url)` 为空，**未建 run** | 422 |
| B7 | 无 pending | sync/workflow | 不建 run，`{count:0, runs:[], failed:[]}`，**非错误** | 200 |
| B8 | **同步等待 vs 立即返回分界** | 两组对照 | legacy 阻塞至终态；`/workflow` 同步段仅"预检+建 run+扇出"（毫秒级）后立即返回 run_id，执行在后台线程 | 200 |
| B9 | 启动成功后图内失败（空标题/门禁拒绝） | 两新端点 | run 落库 `status=failed` + `error`，**不影响 HTTP 200**（启动已成功）；客户端靠轮询发现 | 200 → 轮询见 failed |
| B10 | `kind` 非法值 / `article_id` 类型错 | GET /runs | FastAPI 校验拒绝 | 422（数组型 detail） |
| B11 | 老 run（无 kind 数据） | /runs 三端点 | 列 `DEFAULT 'publish'`，读出即 `publish`，零迁移 | 200 |
| B12 | 双路径并发（legacy + workflow 同文同平台） | — | per-key 互斥保证串行不并发；update 为覆盖式写（幂等），切流文档标注禁双调（R4） | — |

---

## 6. 错误码总表

| HTTP | detail 形状 | 触发条件 | 出现端点 |
|---|---|---|---|
| 200 | — | 启动成功（含 `count=0`、含 run 后续 failed——**run 失败不是 HTTP 错误**） | 1–5 |
| 401 | 字符串 | 配置了 `api_token` 且缺失/错误的 `X-API-Token`（全局中间件） | 全部 |
| 404 | 字符串 | `文章 {aid} 不存在`（update/workflow 启动预检）；`run 不存在`（GET detail） | 1、4 |
| 409 | 字符串 | ① `工作流引擎已通过 config workflow.enabled=false 禁用`；② resume：`run 不存在` / `状态非 waiting_human` / `正在执行中` | 1、2、5 |
| 422 | **字符串**（业务） | `没有已发布实例可更新，先 publish`（update/workflow 无目标，未建 run）；防御性：启动期其他 ValueError | 1 |
| 422 | **数组**（请求校验） | Pydantic/FastAPI 校验失败：body 字段类型错、`aid` 非整数、`kind` 非枚举值 | 1–5 |

> 实现核对：api.py 现状仅用 404/409/422(+401 中间件)，本契约**不引入新错误码**。

---

## 7. 兼容性说明（逐消费方）

### 7-A Vue 前端（`web/src/api.js`、`web/src/stores/hub.js`）

| 端点 | 变化性质 | 消费方要改吗 |
|---|---|---|
| 两新端点 | **纯新增**（前端未调用） | **不改**。可选增强：更新/同步按钮切换到 workflow + 轮询（架构 §10 明确"前端新 UI"本阶段不做） |
| GET /runs | **向后兼容增强**：query 可选、响应项加 `kind` | **不改**。`hub.js loadRuns` 按字段读取，多余字段无感；`waitingRuns` 过滤按 `status`，不受 `kind` 影响 |
| GET /runs/{id} | **向后兼容增强**：加 `kind`；`checkpoint.node` 出现新节点名 | **不改**。`_pollWorkflowRows` 只读 `status/result/error`，节点名仅作展示 |
| POST /runs/{id}/resume | **零变化** | **不改** |
| legacy /update、/sync/pending、/refresh | **冻结**（§7 附） | **不改** |
| `dry_run` 类型陷阱 | 响应中 `dry_run` 是 `0\|1` 数字（SQLite 直出，现状） | **不改、不许"顺手"转 boolean**（真改了才破坏现状兼容） |

### 7-B MCP（`server/mcp_server.py`）

| 项 | 性质 | 说明 |
|---|---|---|
| 两个 HTTP 新端点 | **对 MCP 纯新增** | MCP 不经 HTTP，直调 runner/Hub——本契约不迫使其改动 |
| `update_article` / `sync_pending` 切流 | **行为变化**（属 m5-architecture §6.4，backend 实施，非本契约强制） | 返回形状保持 legacy（`update_article` 仍返回 results 数组；`sync_pending` 组装 `[{article_id,title,platforms,result}]` + 附 `run_ids`）；deadline **900s**（publish 的 300s 不够，`delay_article` 30–90s×N）；**仅 run_id/run_ids 为空才回退 legacy，启动后绝不回退防双发** |
| `refresh_platform` | **不变** | §1.4 永久裁定不接入 |
| 13 工具名单/语义 | **不变** | agent 生态零适配 |

### 7-C legacy 端点现状记录（**冻结**，硬约束 b——只记录，不改）

| 端点 | 请求（现状） | 响应（现状） | 裁定 |
|---|---|---|---|
| POST `/articles/{aid}/update` | `UpdateIn{platforms?: string[]\|null, account="default"}`（**无 dry_run**） | 同步：`[{platform, ok, error?}]` 或 `{"skipped":"没有已发布实例可更新，先 publish"}` | 语义冻结，回退路径 |
| POST `/sync/pending` | 无 body | 同步：`[{article_id, title, platforms, result}]` | 语义冻结，回退路径 |
| POST `/refresh/{platform}` | query `limit=50` | 同步：含 `count`（抓回篇数） | **永久保留**（§1.4 裁定，不接入引擎） |

---

## 8. OpenAPI 风格 YAML（结构化契约，字段名逐字）

```yaml
paths:
  /articles/{aid}/update/workflow:
    post:
      operationId: updateWorkflow
      summary: 启动原地更新工作流（立即返回 run_id）
      parameters:
        - { name: aid, in: path, required: true, schema: { type: integer } }
      requestBody:
        required: false
        content:
          application/json:
            schema: { $ref: '#/components/schemas/WorkflowUpdateIn' }
      responses:
        '200':
          description: run 已启动，后台执行中
          content:
            application/json:
              schema: { $ref: '#/components/schemas/WorkflowStartOut' }
        '404': { $ref: '#/components/responses/ErrString' }   # 文章 {aid} 不存在
        '409': { $ref: '#/components/responses/ErrString' }   # 引擎禁用
        '422': { $ref: '#/components/responses/Err422Both' }  # 业务(字符串)或校验(数组)

  /sync/pending/workflow:
    post:
      operationId: syncPendingWorkflow
      summary: 发现 pending 并按文章扇出 update run（一文一 run）
      requestBody:
        required: false
        content:
          application/json:
            schema: { $ref: '#/components/schemas/WorkflowSyncIn' }
      responses:
        '200':
          description: 扇出完成（count=0 非错误）
          content:
            application/json:
              schema: { $ref: '#/components/schemas/SyncStartOut' }
        '409': { $ref: '#/components/responses/ErrString' }   # 引擎禁用

  /runs:
    get:
      operationId: runsList
      summary: 运行列表（新增 kind/article_id 过滤，向后兼容）
      parameters:
        - { name: limit, in: query, required: false, schema: { type: integer, default: 50 } }
        - { name: kind, in: query, required: false,
            schema: { type: string, enum: [publish, update], default: null } }
        - { name: article_id, in: query, required: false,
            schema: { type: integer, default: null } }
      responses:
        '200':
          description: created_at DESC；缺省不过滤 kind
          content:
            application/json:
              schema: { type: array, items: { $ref: '#/components/schemas/RunListItem' } }
        '422': { $ref: '#/components/responses/Err422Both' }

  /runs/{run_id}:
    get:
      operationId: runDetail
      summary: 运行详情（新增 kind；checkpoint.node 出现 update 图节点名）
      parameters:
        - { name: run_id, in: path, required: true, schema: { type: string } }
      responses:
        '200':
          description: 详情（含 result/checkpoint 实时进度）
          content:
            application/json:
              schema: { $ref: '#/components/schemas/RunDetail' }
        '404': { $ref: '#/components/responses/ErrString' }   # run 不存在

  /runs/{run_id}/resume:
    post:
      operationId: runResume
      summary: 恢复挂起 run（契约零变化；服务端按 kind 路由图）
      parameters:
        - { name: run_id, in: path, required: true, schema: { type: string } }
      requestBody:
        required: false
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ResumeIn' }
      responses:
        '200':
          description: 已恢复执行
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ResumeOut' }
        '409': { $ref: '#/components/responses/ErrString' }   # 不存在/非 waiting_human/执行中

components:
  schemas:
    WorkflowUpdateIn:
      type: object
      properties:
        platforms:
          type: array
          items: { type: string }
          nullable: true
          default: null
          description: null/缺省/[] 等价 = 全部可更新实例（legacy 真值语义）
          example: ["csdn", "zhihu"]
        account:  { type: string,  default: "default", example: "default" }
        dry_run:  { type: boolean, default: false, example: false }
      additionalProperties: false
      example: { platforms: ["csdn", "zhihu"], account: "default", dry_run: false }

    WorkflowStartOut:
      type: object
      required: [run_id, status, poll]
      properties:
        run_id:  { type: string, minLength: 12, maxLength: 12, example: "a1b2c3d4e5f6" }
        status:  { type: string, enum: [running], example: "running" }
        poll:    { type: string, example: "/runs/a1b2c3d4e5f6" }

    WorkflowSyncIn:
      type: object
      properties:
        account: { type: string,  default: "default", example: "default" }
        dry_run: { type: boolean, default: false,     example: true }
      additionalProperties: false

    SyncStartOut:
      type: object
      required: [count, runs, failed]
      properties:
        count: { type: integer, minimum: 0, example: 2 }
        runs:
          type: array
          items:
            type: object
            required: [article_id, title, run_id]
            properties:
              article_id: { type: integer, example: 3 }
              title:      { type: string,  example: "深入 LangGraph" }
              run_id:     { type: string,  example: "a1b2c3d4e5f6" }
        failed:
          type: array
          description: 启动失败篇（按篇隔离，不升级为全局错误）
          items:
            type: object
            required: [article_id, title, reason]
            properties:
              article_id: { type: integer, example: 7 }
              title:      { type: string,  example: "另一篇" }
              reason:     { type: string,  example: "文章 7 不存在" }

    RunListItem:
      type: object
      required: [id, article_id, title, platforms, status, error, dry_run,
                 kind, human_task, summary, created_at, updated_at]
      properties:
        id:          { type: string,  example: "a1b2c3d4e5f6" }
        article_id:  { type: integer, example: 3 }
        title:       { type: string,  example: "深入 LangGraph" }
        platforms:   { type: array, items: { type: string }, example: ["csdn"] }
        status:      { type: string, enum: [running, waiting_human, done, failed] }
        error:       { type: string, example: "" }
        dry_run:     { type: integer, enum: [0, 1], description: '历史返回数字，勿改布尔' }
        kind:        { type: string, enum: [publish, update], description: '新增；存量行=publish' }
        human_task:  { type: object, nullable: true,
                       properties:
                         platform: { type: string }
                         message:  { type: string }
                         edit_url: { type: string } }
        summary:     { type: object, nullable: true, additionalProperties: true }
        created_at:  { type: number, example: 1758547200.12 }
        updated_at:  { type: number, example: 1758547260.45 }

    RunDetail:
      allOf:
        - $ref: '#/components/schemas/RunListItem'
        - type: object
          required: [result, checkpoint]
          properties:
            result:
              type: object
              properties:
                results:    { type: array, items: { type: object, additionalProperties: true } }
                decisions:  { type: array, items: { type: object, additionalProperties: true } }
                summary:    { type: object, additionalProperties: true }
                human_task: { type: object, nullable: true, additionalProperties: true }
            checkpoint:
              type: object
              description: update 图可能出现 next_target/update_instance 等新节点名
              properties:
                node:             { type: string, example: "update_instance" }
                current_platform: { type: string, example: "csdn" }
                attempts:         { type: integer, example: 1 }
                queue_left:       { type: integer, example: 1 }

    ResumeIn:                       # 零变化，逐字沿用
      type: object
      properties:
        approved: { type: boolean, default: true,  example: true }
        note:     { type: string,  default: "",    example: "" }

    ResumeOut:                      # 零变化，逐字沿用
      type: object
      required: [run_id, status]
      properties:
        run_id: { type: string, example: "a1b2c3d4e5f6" }
        status: { type: string, enum: [running], example: "running" }

    ErrorString:                    # FastAPI HTTPException 统一形态
      type: object
      required: [detail]
      properties:
        detail: { type: string, example: "文章 3 不存在" }

  responses:
    ErrString:
      description: 业务错误（detail 为字符串）
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorString' }
    Err422Both:
      description: 422 双形态——业务为字符串 detail；请求校验为数组 detail
      content:
        application/json:
          schema:
            oneOf:
              - $ref: '#/components/schemas/ErrorString'
              - type: object
                properties:
                  detail:
                    type: array
                    items:
                      type: object
                      properties:
                        loc:  { type: array, items: { type: string } }
                        msg:  { type: string }
                        type: { type: string }
```

---

## 9. 关键决策与给 backend 的注记

| # | 决策 | 取舍理由 |
|---|---|---|
| D-A | update/workflow 的 `ValueError` 按文案分流 404/422，不照抄 publish 的"一律 404" | 无目标实例报 404 会误导调用方去查文章是否存在；架构 §6.1 明确 422 语义 |
| D-B | `platforms: []` ≡ `null` ≡ 缺省 = 全部可更新实例 | legacy `if platforms:` 空数组本就不过滤；拒绝 `[]` 是行为倒退 |
| D-C | sync 响应加 `failed[]`（additive 字段，底稿未定义部分失败） | 否则 `count:0` 无法区分"无 pending"与"全启动失败"，MCP 回退判定（run_ids 空才回退）失去依据；对只读 `runs/count` 的消费方是纯增量 |
| D-D | 单篇启动失败不升级为全局 4xx | 失败按篇隔离是 ADR-008 一文一 run 的核心收益，全局报错会让好篇陪葬 |
| D-E | resume 的"不存在→409"怪癖如实冻结 | 硬约束：resume 契约零变化；修正它属于破坏性变更，留给未来版本 |
| D-F | 错误码集 = api.py 现状 {401,404,409,422}，不引入 400/500 语义化 | 约束要求与现状一致；未知启动错误防御性归 422 |

**给 backend-engineer 的三个重点**：
1. **错误映射是最大坑**：两个新端点同步段要把 `ValueError` 按文案分流（404/422），409 判断在最前；`/runs` 三端点不做引擎禁用检查（现状 GET 无 409）。
2. **runner.start(kind='update') 的 platforms 解析**：null/`[]` → 查"全部可更新实例"，空集 → `ValueError('没有已发布实例可更新，先 publish')`；kind 写入 meta 行，`list/get` 补 `kind` 列输出、老行默认 `publish`。
3. **Pydantic 模型**：`WorkflowUpdateIn`（**无 draft_only**）、`WorkflowSyncIn`（body 可省略，用默认实例）、`ResumeIn` 一字不动；`additionalProperties: false` 与现状 `BaseModel` 宽松行为保持一致即可（现状未 forbid，勿收紧造成老客户端 422）。
