# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
