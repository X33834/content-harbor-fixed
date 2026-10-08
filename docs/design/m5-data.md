# M5 数据层变更规范：workflow_runs 加 kind 列 + 复合索引

> 日期：2026-09-22 · 状态：定稿（本文件由主理人补位产出——database-engineer 因 429 配额缺位；依据 m5-architecture.md §5.1/§5.2 + workflows/runner.py _SCHEMA 现状）
> 执行者：Phase 3 backend（本文即实现规格，照做零猜测） · 只允许动 `data/workflow.db`，**hub.db 零改动**

## 1. 幂等 DDL 原文（可直接复制进 workflows/runner.py）

新库路径：`_SCHEMA` 建表时**直接带 kind 列**（新建 db 天然就位）。
存量库路径：SQLite 的 `ALTER TABLE ADD COLUMN` **不支持 IF NOT EXISTS**，必须先探测：

```python
# workflows/runner.py __init__ 内，executescript(_SCHEMA) 之后执行（幂等，重复无害）
try:
    cols = [r[1] for r in self._meta.execute(
        "PRAGMA table_info(workflow_runs)").fetchall()]
    if cols and "kind" not in cols:
        self._meta.execute(
            "ALTER TABLE workflow_runs "
            "ADD COLUMN kind TEXT NOT NULL DEFAULT 'publish'")
    self._meta.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_kind "
        "ON workflow_runs(kind, created_at DESC)")
    self._meta.commit()
    self._mig_error = ""
except Exception as e:
    self._mig_error = str(e)   # 迁移失败：拒绝服务 update 新端点（R6），publish/legacy 不受影响
```

配套 `_SCHEMA` 改动（新库路径）：`workflow_runs` 建表列中加
`kind TEXT NOT NULL DEFAULT 'publish'`；**索引不放 _SCHEMA**（老库上 `CREATE INDEX idx_runs_kind`
会因列不存在而在 executescript 阶段炸掉整个初始化——索引必须等"列已确保存在"后建，即上面迁移块内）。

## 2. 存量行兼容论证

- `kind TEXT NOT NULL DEFAULT 'publish'`：ALTER ADD COLUMN 带非空 DEFAULT 时，**存量行立即读出 'publish'**，无需回填 UPDATE；
- 既有读取路径（list/get/resume）对缺省值统一兜底 `d.get('kind') or 'publish'`，双保险；
- publish 图代码路径逐字不变（kind 缺省即 publish），R1 风险面为零。

## 3. 失败回滚步骤

1. **迁移失败（`_mig_error` 非空）**：update/sync 新端点返回 500 语义错误（runner.start 抛 RuntimeError），
   legacy `/update`、`/sync/pending`、publish 全部不受影响；修复后重启服务自动重试迁移。
2. **兜底（架构 §5.2/R6 允许）**：停服 → 删 `data/workflow.db` → 重启。**代价边界**：丢的是
   checkpoint 断点（挂起 run 的恢复能力）与 run 历史审计——**不丢文章、发布实例、登录态**（全在 hub.db/profiles）。
   适用条件：无 waiting_human 挂起 run 待恢复时。有挂起 run 时先走备份恢复（见 §4）。
3. **回滚整个 M5**：`git checkout phase-2 -- .`（回到切流前）+ 删 `workflows` 内 update 相关代码
   （PublishState/publish 图零改动，update 图整文件级弃用即回退，ADR-007）。

## 4. 备份清单（回应 AUDIT 遗留「data/ 单副本无备份」M 级债）

| 资产 | 内容 | 频率 | 保留 | 明文处置 |
|---|---|---|---|---|
| `data/hub.db` | 文章/发布实例/jobs/账号状态 | 每次发布后或每日 | ≥7 天滚动 | 无凭据，可直接备份 |
| `data/workflow.db` | run 历史 + checkpoint（含挂起断点） | 每次 run 终态后或每日 | ≥7 天滚动 | 无凭据 |
| `data/profiles/*.auth.json` | **登录快照（含 session cookie）** | 每次登录/保鲜后（自动） | 最新 1 份 + `.tmp` 原子写 | **敏感**：备份目标须本机私有目录，禁止入库/上传 |
| `data/profiles/*/`（浏览器 profile） | 登录态 L1 层 | 可选（auth.json 已兜底） | — | **敏感**：同上 |
| `config.json` | AI/平台凭据明文 | 变更时手动 | 最新 1 份 | **敏感**：禁止入库（.gitignore 已覆盖），备份到本机私有目录 |

最小可用命令（手工）：
`cp data/hub.db data/hub.db.bak && cp data/workflow.db data/workflow.db.bak && cp -r data/profiles data/profiles.bak`
（backup 时服务须停写；SQLite 在线备份更稳的做法是用 `sqlite3 .backup`，M6 可做成脚本，本阶段给手工命令即可。）

## 5. 索引影响评估

`(kind, created_at DESC)` 复合索引直接命中 `GET /runs` 的两种新过滤：
`WHERE kind=? ORDER BY created_at DESC LIMIT ?` 与 `WHERE kind=? AND article_id=?`（article_id 等值过滤在
索引前缀不匹配时走全扫——run 表量级为百行内，可忽略；如未来 run 上万，再加 `(article_id, created_at)` 索引即可，YAGNI 现在不加）。
写入侧：每次 run 建/更新多一次索引维护，量级无感。
