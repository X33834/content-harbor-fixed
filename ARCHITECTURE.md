# ARCHITECTURE.md — AI 内容中台架构

| 项 | 值 |
|---|---|
| 版本 | 0.4.0-fix |
| 日期 | 2026-10-09 |
| 状态 | 维护中 |
| 唯一真理源 | ARCHITECTURE.md + AGENT.md |

## 1. 系统概览

AI 内容中台：写作 → 合规 → 多平台发布 → 验证 → 人机协作收尾。

- 技术栈：Python 3.13 + FastAPI + SQLite + Patchright Playwright + Vue3/Element Plus
- 架构模式：统一任务引擎 (TaskManager) + 平台适配器（11 个）

## 2. 当前架构

```
┌──────────────────────────────────────────────────┐
│                   浏览器 / 用户                      │
│                     Vue3 前端                       │
│              (Element Plus, 消息驱动)                │
└──────────────────────┬───────────────────────────┘
                       │ HTTP POST /api/v1/*
                       ▼
┌──────────────────────────────────────────────────┐
│                  FastAPI Router                    │
│                  api/hub.py                       │
│          api/v1/* → get_task_manager()            │
└──────────────────────┬───────────────────────────┘
                       │ submit("publish"/"update"/
                       │        "sync"/"refresh"/
                       │        "login"/"assist")
                       ▼
┌──────────────────────────────────────────────────┐
│               TaskManager (tasks.py)               │
│            统一任务引擎，串行 Worker                 │
│        SQLite 持久化 → 确定性分流 → 恢复             │
└───┬──────────────┬──────────────┬─────────────────┘
    │              │              │
    ▼              ▼              ▼
┌────────┐   ┌──────────┐   ┌──────────┐
│  Hub    │   │   AI     │   │   Gate   │
│ (pblish │   │ (OpenAI  │   │ (AIGC    │
│ .svc)   │   │  compat) │   │ 合规)    │
│ +11 适配器│   └──────────┘   └──────────┘
└────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  DB (db.py, 单文件 SQLite, tasks 表)               │
│  Browser (Patchright Chromium, per-profile)        │
│  Config (config_unified.py)                        │
└──────────────────────────────────────────────────┘
```

## 3. 目录结构 (post-fix)

```
content-harbor/
├── backed/
│   ├── app/
│   │   ├── factory.py          # FastAPI 工厂，lifespan
│   │   ├── routes/
│   │   │   └── (挂载 hub.py router)
│   │   └── middleware/
│   │       └── (认证中间件)
│   ├── api/
│   │   ├── hub.py              # 核心 REST 入口
│   │   └── v1/
│   │       └── (hub 调度至 TaskManager)
│   ├── core/
│   │   ├── permissions.py
│   │   ├── human_click.py
│   │   └── security.py
│   ├── service/publishing/
│   │   ├── hub.py              # Hub 编排器
│   │   ├── db.py               # 单源持久化层
│   │   ├── browser.py          # Patchright 适配
│   │   ├── gate.py             # AIGC 合规门禁
│   │   ├── ai.py               # OpenAI 兼容 LLM 调用
│   │   ├── tasks.py            # TaskManager
│   │   ├── humanize.py         # 人机延迟/点击次数模拟
│   │   ├── observability.py    # 日志/指标
│   │   └── adapters/
│   │       ├── __init__.py     # @register 注册器
│   │       ├── base.py         # PlatformAdapter 基类
│   │       ├── zhihu.py
│   │       ├── xiaohongshu.py
│   │       ├── wechat.py
│   │       ├── toutiao.py
│   │       ├── bilibili.py
│   │       ├── douyin.py
│   │       ├── weibo.py
│   │       ├── juejin.py
│   │       └── (其余 3 个)
│   ├── config_unified.py       # 统一配置
│   └── cli.py                  # CLI 入口
├── web/src/                    # Vue3 前端源码
├── deploy/                     # Docker / 部署脚本
└── pyproject.toml
```

## 4. 任务引擎 (TaskManager)

核心调度流程：

1. **提交**：`submit("publish"|"update"|"sync"|"refresh"|"login"|"assist")`
   - 写入 SQLite `tasks` 表
   - 返回 `task_id`（UUID hex[:10]）
   - 202 Accepted + Location

2. **Worker 线程**：串行处理，一次一个任务
   - 状态机：`pending` → `running` → 结果

3. **确定性分流 (Triage)**：
   - 匹配 `HUMAN_HINTS` → `waiting_human`
   - 匹配 `RETRY_HINTS` → 指数退避重试（`MAX_ATTEMPTS = 3`）
   - 其他 → `fail`

4. **人机协作恢复**：`POST /tasks/{task_id}/resume`（approved=true/false）

## 5. 平台适配器

| 平台 | 认证方式 | 发布类型 | 支持更新 |
|------|---------|---------|---------|
| 知乎 | Browser | 文章 | 是 |
| 小红书 | Browser | 图文 | 否 |
| 微信公众号 | Browser | 图文 | 否 |
| 头条号 | Browser | 文章 | 否 |
| B站 | Browser | 视频/专栏 | 否 |
| 抖音 | Browser | 视频 | 否 |
| 微博 | Browser | 博文 | 否 |
| 掘金 | API | 文章 | 是 |
| SegmentFault (SF) | API | 文章 | 否 |
| 博客园 | XML-RPC | 文章 | 是 |
| CSDN | Browser/API | 文章 | 是 |

## 6. 登录态永续

4 层保障机制：

1. **Profile Cookies**：Patchright Chromium 持久化 profile 目录
2. **auth.json 快照**：关键 cookie 序列化到本地 JSON
3. **Check/Refresh 接口**：定期检查并刷新登录态
4. **启动恢复**：服务启动时从 auth.json 恢复浏览器 session

## 7. API 端点

### 任务接口 (`api/hub.py`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/publish` | 提交发布任务 |
| POST | `/api/v1/update` | 提交内容更新任务 |
| POST | `/api/v1/sync` | 同步平台状态 |
| POST | `/api/v1/refresh` | 刷新登录态 |
| POST | `/api/v1/login` | 执行登录流程 |
| POST | `/api/v1/assist` | 人机协作辅助 |
| GET  | `/api/v1/tasks` | 查询任务列表 |
| GET  | `/api/v1/tasks/{task_id}` | 查询任务详情 |
| POST | `/api/v1/tasks/{task_id}/resume` | 恢复等待人工任务 |
| GET  | `/api/v1/tasks/{task_id}/status` | 轻量状态查询 |

### AI 写作 (`api/v1`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/ai/write` | AI 生成文章 |
| POST | `/api/v1/ai/rewrite` | AI 改写内容 |
| POST | `/api/v1/ai/polish` | AI 润色/查缺补漏 |

### 出版/人工

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/v1/publications` | 已发布内容列表 |
| GET  | `/api/v1/pending-human` | 待人工处理任务列表 |

## 8. REST / MCP 双入口

### REST 入口（异步）
- 路径：`api/hub.py` → `api/v1/*`
- 流程：`HTTP → get_task_manager() → submit() → 202 + task_id`
- 客户端轮询 `GET /tasks/{id}/status`

### MCP 入口（同步）
- 网关直接调用 `hub.*` 函数
- 绕过 TaskManager，同步返回结果
- 适用：AI Agent 即时读写，无需任务持久化

## 9. 配置与安全

### JWT 鉴权
- 启动时若无显式配置，**自动生成** `api_token`，警告日志输出
- 生产环境必读入环境变量 `HARBOR_SECRET_KEY`

### 数据库
- 默认：`sqlite:///content_harbor.db`
- 生产：通过 `HARBOR_DATABASE_URL` 指定（如 PostgreSQL 连接串）

### 关键环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HARBOR_SECRET_KEY` | JWT 签名密钥 | 启动时自动生成 |
| `HARBOR_DATABASE_URL` | 数据库连接 URL | `sqlite:///content_harbor.db` |
| `HARBOR_API_TOKEN` | API 访问令牌 | 自动生成 |

## 10. 风险与回滚

| 风险 | 影响 | 缓解 |
|------|------|------|
| 平台 UI 变更 | 适配器 BadGateway | 更新 adapters/ 模块 |
| 浏览器崩溃 | 任务进入 `waiting_human` | 重启服务 → 残存任务自动恢复 |
| 登录态失效 | 平台发布失败 | 4 层永续重新激活 |
| 数据库锁竞争 | SQLite 并发受限 | LockedConnection (RLock) |
| LLM 服务不可用 | AI 写作/改写失败 | 三轮指数退避，之后置 `fail` |
