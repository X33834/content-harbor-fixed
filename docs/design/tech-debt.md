# tech-debt.md — 技术债台账与还债计划

> 日期：2026-09-22 · 基线：AUDIT.md 已修 12 项 · 本阶段**只读盘点**（本文件为唯一新增）
> 定级方法：3×3 矩阵 = 发生概率(H/M/L) × 影响(H/M/L)，乘积 6–9=H / 3–4=M / 1–2=L；
> 排序键 =（概率×影响）÷ 还债成本，同分先还"回滚难度低"的。

## 一、债务台账（12 项）

| # | 债项 | 位置 | 概率×影响 | 定级 | 还债成本 | 收益 | 建议时机 | 回滚难度 | 一句话还债方向 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **12 项修复 + workflows/ + 新前端全部未提交，无版本基线** | git 工作区（32 modified / 20+ untracked） | M×H=6 | **H** | 0.5d | AUDIT 的"可回退"承诺落地；误操作可恢复 | **立即**（本阶段只读，未执行） | 极低（只加不改） | 跑一遍双 smoke 后分 3 笔 commit：修复+引擎+前端文档，形成回退基线 |
| 2 | **无一键回归门禁**：smoke 靠手敲、无 CI、mock E2E 不在回归入口 | scripts/ tests/（无 .github） | H×M=6 | **H** | 0.5d | 改动后 10 分钟验证 12 项修复不复发 | 紧随 #1、先于一切重构 | 极低（纯新增） | 新增 `scripts/check_all.sh`：py_compile + smoke_workflow + smoke_hitl + vite build，提交前必跑 |
| 3 | **update/sync 仍走 legacy**，双路径并存（绞杀者未完成）。~~refresh~~ 经 architect 裁定**不接入引擎、永久保留 legacy**（单步只读、无分支无决策，引擎三价值点全用不上——见 m5-architecture.md §1.4），已从本债项剥离 | core/service.py:581-633、api.py:334/339 | H×M=6 | **H** | 1.5–2.5d | 原地更新纳入引擎：断点恢复/分诊/decisions 留痕 | M5（Top3 第 3 步） | 中（旧端点原样保留 + `workflow.enabled` 一键回退） | update 切新 `/update/workflow` 端点、sync 走编排层扇出（一文一 run）——publish_single 已抽出，动作节点换 adapter.update 即可；refresh 不动 |
| 4 | 任务态存内存（PUBLISH_TASKS/LOGIN_TASKS），重启丢状态 | server/api.py:249,405 | M×M=4 | **M** | 1d | 重启后任务可查、轮询不落"unknown" | 与 #5 同批 | 低（只加表不动逻辑） | 任务状态落已有 jobs 表，内存字典降级为缓存层 |
| 5 | 共享驱动进程级崩溃需整进程重启 | core/browser.py:103 `_get_shared_pw` | L×H=3 | **M** | 1d（监控+拉起） | 崩溃自愈、免人工盯 | **发生再议**（见"不还清单"） | 中（单例是刚修好的 P0，动它风险大） | 治标不动单例：外挂健康端点 + 进程守护自动拉起，崩了 30s 内恢复 |
| 6 | requirements 全 `>=` 未锁版本，与 ADR-001"M1 锁定版本"矛盾 | requirements.txt | M×M=4 | **M** | 0.2d | 环境可复现，langgraph 漂移可控 | 随 #1 同批 | 低 | freeze 精确版本存 `requirements.lock`，安装脚本改用 lock |
| 7 | 构建产物入库且新旧 hash 混杂（旧 static 已删未提交、新 static 未跟踪） | server/static/ | H×L=3 | **M** | 0.3d | git diff 干净，build 不再污染状态 | 随 #1 | 低（产物可再生） | 定规矩二选一：static 全 gitignore + 部署时 build；或每次 build 后随代码同 commit |
| 8 | 裸 `except Exception` 151 处 + `print` 22 处未收编 observability | core/ server/ workflows/ | M×M=4 | **M** | 渐进（不专项） | 排障从"猜"变"查" | 随触随改 | 低 | 新代码强制走 obs.events；存量只在改到的函数顺手收窄 except 范围 |
| 9 | data/ 单副本无备份（auth.json 登录资产 + hub.db 文章库） | data/（已 gitignore，无第二份） | L×H=3 | **M** | 0.5d | 磁盘事故不重扫码、文章不丢 | 本周（低成本高杠杆） | 极低（纯新增） | `scripts/backup_data.sh` 每日拷 data/ 至带日期目录，保留 N 份 |
| 10 | 双 lockfile 并存（pnpm-lock.yaml + package-lock.json） | web/ | M×L=2 | **L** | 0.1d | 安装一致性 | 下次动依赖时 | 极低 | 定 pnpm 或 npm 其一，删另一份 |
| 11 | docs/ 未成型：ARCHITECTURE/AUDIT 散落根目录，docs/ 仅 screenshots | 根目录、docs/ | L×M=2 | **L** | 0.3d | 文档可导航、根目录只留入口 | 下次文档回写批处理 | 极低（git mv） | 建 docs/{architecture,audit,design}/，根目录 README 留指针 |
| 12 | 掘金后台 2–3 个测试草稿 | 掘金平台侧 | L×L=1 | **L** | 5min | 后台干净 | 随手 | 无（平台侧删除） | 非工程债：平台后台手动删即可 |

## 二、Top3 还债排期

| 序 | 债项 | 预估工作量 | 前后依赖 | 小步路径（每步行为不变、可回退） |
|---|---|---|---|---|
| **T1** | #1 版本基线入库 | **0.5d** | 无前置——是 T2/T3 的前置 | ①跑 check 预检 → ②commit"12 项修复" → ③commit"workflows 引擎+docs" → ④commit"前端改版"；三笔互相独立可单独 revert |
| **T2** | #2 一键回归门禁（连带 #6 锁版本、#7 static 规矩） | **0.5d** | **强依赖 T1**（基线在手才谈得上"检出回归"） | ①写 check_all.sh → ②实跑全绿 → ③写进 README 提交约定；不改任何业务代码 |
| **T3** | #3 update/sync 切流引擎（即 M5 提前起刀；refresh 按 architect 裁定不切） | **1.5–2.5d** | **前置 0**：update_single 抽取（architect m5-architecture §10 第 1 步，行为逐字不变，动 legacy update() 本体=R3(H) 风险源）**必须最先完成并验完**，否则切流步骤一律不开工；**强依赖 T2**（动主路径必须有回归网） | ⓪update_single 抽取（0.5d，纯重构冒烟）→ ①切 update 单平台（1d，新 `/update/workflow` 端点，legacy 保留）→ ②切 sync_pending（0.5–1d，编排层扇出一文一 run）→ ③**卡口：S1–S6 冒烟门禁全绿（smoke_workflow+smoke_hitl+legacy/引擎双跑 DB diff）通过之后**才标 strangler/deprecated 注记（过早标注=宣告切流完成，回退窗口语义乱）——注意 S1–S5（update 特有冒烟案）**尚不存在，需 backend §10 第 6 步新写**，S6=现有 smoke_workflow+smoke_hitl 回归电池；即 ③ 卡口 = 新冒烟案产出 + 全绿，非现成复跑；每步跑 check_all + dry_run 验证，`workflow.enabled=false` 全程可退；**回退仅限启动失败，启动后绝不回退防双发**（与 publish 同款） |

**还债配额建议**：T1+T2 合计 1d，本周一次还清（纯卫生，不占功能节奏）；T3 = 前置⓪ + 2 切流小步 + 门禁后注记，单步 ≤1d，按 10–15%/迭代配额夹在功能间做，不整块占交付窗口。

## 三、明确"不建议现在还"的债（4 项）

| 债项 | 定级 | 不还的理由 | 触发条件（何时重提） |
|---|---|---|---|
| element-plus 943KB 单包/首屏懒加载 | L（L×M=2） | **收益不抵成本**：单用户内网场景首屏慢几百 ms 无感；且已按需引入，943KB 是 vite `manualChunks` 把 element-plus 强制合成单 chunk 所致——root cause 已定位，真要还只需删 manualChunks 一条目（0.5h），不值得现在占排期 | 用户/外部访问感知卡顿时 |
| 共享驱动崩溃自愈（#5） | M | **概率低 × 改动风险高**：原结构同样有此病非新债；单例刚作为 P0 修复完成（9/9 全绿），现在动它=高风险低频收益 | 首次真实崩溃发生，或部署到无人值守环境时 |
| Hub 上帝类 service.py / api.py 单文件拆分 | M | **违反绞杀者战略（ADR-003）**：架构明确"适配器与 Hub 原样保留"，整体拆分=大爆炸重写，正是 ADR 否决的备选；切流时会顺带瘦身 | T3 完成、双路径收敛（M5 收官）后按触碰频率自然拆 |
| 掘金测试草稿清理（#12） | L | **非代码债**：平台侧数据，工程手段清理=过度工程 | 用户下次登录顺手删 |

## 四、权衡说明（对交付的影响）

- T1/T2 共 1d，全是"新增文件+提交"，**零业务行为变更**，对交付节奏无挤压。
- T3 是唯一动主路径的债：靠 T2 的回归网 + strangler 保留旧端点 + `workflow.enabled` 开关三重护栏，任何一步可独立回退；按小步拆分后单步 ≤1d，不形成阻塞窗口。
- 不还清单里 4 项合计 ≈ 3d 成本，省下全部让给交付；触发条件已写死，防止后续阶段重复提案。
