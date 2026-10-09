# Changelog

---

## [0.6.0] - 2026-10-09

### 新增：多模型管理

- **8 个 AI Provider 预置**：DeepSeek / OpenAI / Anthropic / Kimi / 通义千问 / 智谱 / Ollama 本地
- **任务分级路由**：写作用 premium，润色用 standard，标签/摘要/大纲/SEO 用 economy
- **自动故障转移**：某个 Provider 连续失败 3 次冷却 2 分钟，自动切到下一可用
- **按请求指定模型**：任意 AI 调用传 `model="provider:model_name"` 绕过路由
- **前端模型下拉**：AI 写稿弹窗新增 Provider · 模型选择，留空走自动路由
- **CLI `--model` / `--provider`**：命令行指定模型和 Provider
- REST: `GET /ai/providers` · `GET /ai/status` (enriched)

### 新增：事件 / 通知系统

- **Webhook 注册**：URL + 事件过滤 + HMAC 签名，事件异步 POST 推送
- **事件类型**：task.ok / task.failed / task.waiting_human / publish.ok / publish.failed 等 10 种
- **站内通知**：环形缓冲最近 200 条，`GET /notifications` 拉取
- **自动禁用僵尸 Webhook**：连续失败 5 次暂停
- **任务完成自动触发事件**：TaskManager 内建 emit 节点
- REST: `GET/POST/PUT/DELETE /webhooks/{id}` · `POST /webhooks/{id}/test` · `GET /notifications`

### 新增：内容质检

- **可读性评分**：基于句长、段落长度、标题密度、代码占比；0-100 + 等级
- **SEO 评分**：TDK 完整度、关键词分布、H 标签结构、图片 alt、内链数
- **近似重复检测**：MinHash + Jaccard 查重，阈值 35%
- **一键运行**：`content_qa()` 返回总分 + 分项 + 改进建议
- 前端编辑器「视图与 AI」下拉新增「内容质检」条目 + 圆形总分图
- REST: `POST /articles/{id}/qa` · `POST /qa/analyze`

### 新增：MCP Server（FastMCP）

- **16 个 MCP Tool**：覆盖文章 / AI 写稿 / 发布 / 任务 / 质检 / 标签 / Provider
- **stdio + SSE** 两种传输，对接 Claude Code / Cursor / Windsurf
- 文件：`mcp_server.py`（项目根目录，独立运行）

### 前端改善

- AI 写稿弹窗增加模型选择器（按 Provider 分组，标注经济/均衡/旗舰）
- 文章编辑器新增「内容质检」菜单项 + 质检报告弹窗（圆形总分 + 可读性/SEO/重复度 + 改时建议）
- Element Plus 改为全局注册（uniplugin 轻量化），包体略大但构建更稳定

---

## [0.5.0] - 2026-10-09

### 新增：AI 工作流完整工具链

- **AI 翻译**：`ai_translate` — Markdown 文章翻译（保留代码块不动）到 en/ja/ko/fr/de
- **配图提示生成**：`ai_image_prompts` — 从正文提炼 3 个英文文生图 prompt（兼容 SDXL/Flux/DALL·E）
- **大纲提炼**：`ai_outline` — 从 Markdown 内容提取标题层级树
- **SEO 元数据**：`ai_seo` — 自动生成 seo_title / seo_description / slug / keywords
- **文章克隆**：`clone` — 复制已有文章为新草稿
- **写作模板**：4 个预置模板（教程/观点/深度剖析/资讯简评）

### 新增：定时发布调度器

- 守护线程每 30 秒轮询 `scheduled_tasks` 表，投递到 TaskManager
- 支持 once / daily / weekly / cron 四种调度类型
- CLI: `schedule-add` / `schedule-list` / `schedule-del` / `schedule-trigger`

### 新增：文章版本管理

- 改文章前自动快照到 `version_history` 表（sha256 去重）
- 回滚 / 行级 diff / AI 改写润色前自动存版本
- CLI: `versions` / `rollback`

### 新增：标签治理

- `tag_stats` 表 + `alias_map` 同义合并
- 合并 / 重命名 / 别名三步治理 + 词云展示
- CLI: `tags` / `tag-sync` / `tag-rename`

### 前端

- 编辑器「视图与 AI」下拉扩展（翻译/配图/大纲/SEO/克隆/版本历史）
- 新 `VersionDrawer` + `AIToolDialog` 组件
- ManagePanel 新增「定时任务」+「标签治理」标签页

### 文档

- ARCHITECTURE.md 新增 D6-D9 + API 路径总览
- CHANGELOG.md 本条目

---

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.1] - 2026-10-09

### 文档打磨

- **README.md 全面重写**：修复所有过时引用（`deplay` → `deploy`、`/api/v1` CRUD 路由、MCP 入口、`markdown-it` → `md-editor-v3`、`server/static` 构建路径）；删除 E2E 测试引用（测试套件已拆除）；更新仓库地址为多镜像表格
- **README.en.md 全面重写**：与中文版内容同步，专注国际开发者视角
- **ARCHITECTURE.md 全面重写**：修复目录结构（不再列举 `xiaohongshu` / `wechat` 等不存在的适配器）、修复 API 路径（删除 `/api/v1/*` 引用）、新增 ADR 设计决策一节（统一任务引擎、Patchright、单实例浏览器、双库合一、异步轮询）
- **CHANGELOG.md 同步更新**

### 浏览器启动修复

- `browser.py` `_find_chrome()` 新增 `/opt/playwright` 搜索根和 `chromium-*/chrome-linux64/chrome` 模式，解决沙箱环境内 Chromium 二进制找不到的问题

### 前端组件打磨

- 字体系统重构：`--font-serif` / `--font-disp` 语义化命名，真正区分展示体与代码块；中英字体栈优化（零外部请求）
- 删除 `App.vue` 中不再使用的 `.fab` 浮动按钮样式残留
- `vite.config.js` 修正 `manualChunks.md` 从 `markdown-it` → `md-editor-v3`；开发代理目标改为 `:8000`（当前默认端口）

## [0.4.0-fix] - 2026-10-09

### 重大清理

- **删除 scaffold 遗留**
  - 移除 `api/v1/` 孤立的 scaffold router
  - 移除 `models/` Pydantic 模型层（无实际依赖）
  - 移除 `schemas/` 校验层（无实际使用）
  - 移除 `repository/` 仓储抽象层（直连 db.py 即可）
  - 移除 `*_service.py` 重复服务层（article_service、account_service、job_service、publication_service、task_service）
  - 合计减少约 800 行无用代码

- **删除幽灵基础设施**
  - 移除 `core/cache.py`（从未被调用，仅定义类）
  - 移除 `core/queue.py`（从未被调用，基于 asyncio.Queue 的空实现）

- **移除 scaffold 遗产**
  - 移除 `events.py`（空事件钩子）
  - 移除 `router.py`（空路由器基础结构）
  - 移除 `config/settings.py`（已统一到 config_unified.py）

- **统一持久化层**
  - 保留 `db.py` 原生 SQLite SQL 作为唯一持久化层
  - 移除 SQLAlchemy ORM 依赖（不再需要 ORM 抽象）
  - 所有表结构定义集中在 `db.py` + `MIGRATIONS` 列表

- **测试清理**
  - 删除 `backed/tests/` 中引用 scaffold 的旧测试文件
  - 待后续补充针对性单元测试与集成测试

### 修复

- **humanize.py**
  - 修复 `human_type` 公式 bug：原公式导致打字速度被 WPS_EM 分母稀释
  - 修复后有效 WPM 从 48-84 提升到配置的 240-420 范围
  - 移除冗余的类封装，改为纯函数

- **observability.py**
  - 删除死代码 `_observe_with_max`（废弃的观察模式）
  - 删除 `M_*` 常量组（从未引用）
  - 删除 monkey-patch 逻辑（破坏函数签名，干扰调试）

- **config_unified.py**
  - `ProductionConfig.secret_key` 改为从 `HARBOR_SECRET_KEY` 环境变量读取
  - `ProductionConfig.database_url` 改为从 `HARBOR_DATABASE_URL` 环境变量读取
  - 缺失时抛出 `ValueError` 而非静默回退到默认值

- **api/hub.py**
  - 移除模块加载时的全局 Hub 副作用
  - 改为惰性单例工厂模式 `get_hub()`
  - 移除导入时的 `from service.publishing.hub import Hub` 全局实例化

- **app/factory.py**
  - `lifespan` 简化为 DB 初始化 + logging 配置
  - 移除 cache/queue 初始化（随幽灵基础设施删除）
  - 移除 scaffold router 注册

- **安全**
  - `api_token` 未配置时自动生成 UUID4
  - 启动时打印警告日志：`Generated api_token=*** — set HARBOR_API_TOKEN in production`
  - 生产模式必须显式指定 token

### 前端修复

- 删除 `App.vue` 中未使用的 `onRefresh` / `refreshing` 状态管理
- 删除 `ArticleList.vue` 中与 ArticleStore 重复的过滤逻辑（单一数据源原则）
- `ArticleEditor.vue` 补全 `is-active-cmd` 样式类（编辑态视觉反馈）

### 重命名

- `deplay/` → `deploy/` （`git mv`，修正拼写错误）

### 依赖更新

- `pyproject.toml`
  - 移除 `sqlalchemy`（不再需要 ORM）
  - 移除 `aiosqlite`（不再需要异步 SQLite）
  - 移除 `aiomysql`（不再需要 MySQL 异步驱动）
  - 移除 `greenlet`（SQLAlchemy 附带依赖）
  - 版本号对齐 `0.4.0-fix`

---

_Template for future entries:_

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
