# M5 架构设计：update / sync_pending / refresh 接入 LangGraph 工作流引擎

> 日期：2026-09-22 · 状态：**已定稿并实施**（S1–S6 冒烟全绿 + publish 回归全绿 + 端点真验通过；D-C 经主理人中转获批）
> 作者：architect（高见远） · 交付对象：api-designer / database-engineer / backend-engineer
> 真理源回写：本文定稿后由 backend-engineer 实施时同步回写 ARCHITECTURE.md（§3.5 新图、ADR-007~009、Changelog）

## 0. 验收对照（六要素 → 章节）

| 验收项 | 章节 |
|---|---|
| ① 三操作逐一裁定 | §1 |
| ② 图拓扑与节点清单（复用/新增） | §3 |
| ③ 状态模型字段级定义（逐字签名） | §4 |
| ④ 接口清单（路径/方法/schema 草案） | §6 |
| ⑤ ≥2 备选方案 + 代价对比（一致性/回滚速度/维护成本） | §7 |
| ⑥ 风险表 H/M/L（3×3 矩阵定级） | §9 |
| 硬约束 a~e 合规自检 | §12 |

---

## 1. 三操作裁定

### 1.1 裁定总表

| 操作 | 裁定 | 一句话理由 |
|---|---|---|
| `Hub.update`（原地更新） | **接入**（新建 update 工作流图） | 与 publish 同构的"多平台循环 + 每平台独立成败"结构，P2/P3/P4 三缺陷在 update 上原样存在，引擎价值点（分诊/挂起/断点/可观测）全部命中 |
| `Hub.sync_pending`（批量同步） | **接入，但作为编排层扇出**（不建独立图） | 它只是"发现 pending 集合 → 按文章分组 → 逐篇 update"的批处理器，无独立节点逻辑；一文一 run 复用 update 图，失败/挂起按篇隔离 |
| `Hub.refresh`（抓列表入库） | **不接入**（保留 legacy，永久裁定） | 单步只读观测操作，checkpoint/interrupt/条件路由三个引擎价值点一个都用不上；接入只产生 run 噪音与维护成本 |

### 1.2 update：接入

**依据（逐条对应引擎价值）**：

1. **失败分诊缺失（P4 同款）**：legacy update 只有 ok/failed 两态，风控/超时/登录失效全靠人肉看 jobs 表重跑。update 触碰平台编辑页，遇到验证码/风控的概率与 publish 同级 → triage（retry/human/skip）直接复用。
2. **无重试（P2 同款）**：legacy `for` 循环零重试；浏览器崩溃类瞬时错误在 publish 已由重试回边解决，update 同样需要。
3. **无人机协作（P3 同款）**：更新途中登录态失效/弹验证码 → 需要 wait_human（recover 场景原样复用：人工排除故障 → 恢复 → 回 update_instance 重试）。
4. **长任务可观测**：多平台 ×（更新耗时 + 30–90s 风控间隔）可达数分钟，legacy 同步 HTTP 必然超时（现状 `POST /articles/{aid}/update` 就是同步端点，多平台已超时风险）。切流后统一 run_id 轮询模型，与 publish 一致。
5. **边际成本低**：拓扑与 publish 高度同构（见 §3），复用节点函数与决策核心，仅新增 4 个薄节点。
6. **Agent 驱动一致性**：MCP `publish_article` 已返回 run_id；`update_article` 若仍同步阻塞数分钟，工具要么超时要么长挂。

**幂等性注记**：update 是"覆盖式写"（打开编辑页替换内容后保存），重复执行=重复写同内容，双发危害远低于 publish（无新帖产生）→ 风险表按 M 而非 H 定级（R4）。

### 1.3 sync_pending：接入（编排层扇出，不建独立图）

**结构分析**：`sync_pending` = `db.get_pending_updates()`（发现）+ 按 `article_id` 分组 + 对每组调 `update(aid, platforms)`（复用）。它没有 update 之外的节点语义。

**裁定方案**：HTTP 端点/MCP 工具承担"发现 + 扇出"：

```
POST /sync/pending/workflow
  → db.get_pending_updates() 分组（与 legacy 同一段 SQL）
  → 逐篇 runner.start(kind='update', platforms=该篇 pending 平台集)
  → 返回 {count, runs:[{article_id, title, run_id}]}
```

**为什么不建 sync 独立图**：
- `workflow_runs.article_id` 是单值列，跨文章大图会破坏 run↔文章 的既有语义（/runs 列表、前端运行记录、审计全部按单文章组织）；
- 一图跨 N 文章时，单篇 wait_human 挂起会阻塞整批恢复，checkpoint 粒度错位；
- 为复刻一个 `for` 循环新建图/State/节点 = 纯复制成本，违反 YAGNI。

**一文一 run 的收益**：失败隔离（A 篇门禁拒绝不挡 B 篇）、挂起隔离（A 篇等人处理，B 照跑）、查询/恢复全套 `/runs` 能力零成本复用、MCP 轮询可按 run 并行。

**legacy `POST /sync/pending` 保留**，仅启动失败（引擎禁用/一篇都没启动）才回退，见 §6.4。

### 1.4 refresh：不接入（架构理由）

1. **无引擎价值点**：单平台 × 单次 `list_articles` 浏览器操作 + 本地 DB upsert——没有分支、没有循环、没有决策点、没有无人机场景（抓列表是只读观测，不会要人去平台后台点确认）。LangGraph 的三大卖点（checkpoint 断点恢复 / interrupt-resume / 条件路由）全部用不上。
2. **重跑成本 ≈ 操作成本**：列表抓取 5–30s，失败直接把错误还给调用方、再调一次即可（幂等 upsert，无双发问题）。为单步操作建 run 元数据 + checkpoint 写盘 + 线程调度，开销可能超过操作本身。
3. **接入的净负债**：`workflow_runs` 被高频只读刷新刷爆（噪音淹没 publish/update 的有效 run）；runner 多养一种 kind；前端运行记录页要为它做过滤。**维护成本 > 收益**。
4. **符合绞杀者原则（ADR-003）**：按价值切，不按清单切。"不接入"是完成评估，不是遗留——本裁定写死在 §1.1，AUDIT 遗留表该行可勾销。

**未来重评触发条件（任一成立才重开评估）**：① refresh 需要多步翻页/增量抓取；② 抓取失败需要分诊而非直接报错；③ 出现"抓取 → 关联 → 修复孤儿记录"的人工协作链。届时按 M5 同款流程补设计。

---

## 2. 总体架构与模块边界

### 2.1 架构风格

**绞杀者增量第二刀**（延续 ADR-003）：publish 主路径已切流验证；本次把 update/sync 按同款模式切流，refresh 永久留在 legacy 并显式标注裁定。适配器层、Hub 浏览器/登录/DB 基础设施零改动。

### 2.2 模块边界与依赖方向

```
server/api.py ────────┐                    ┌──> core.service.Hub.update_single ──> core.adapters（原样）
server/mcp_server.py ─┼──> workflows/runner（kind 路由）
                      │        └──> workflows/graph.py::build_update_graph
                      │                  └──> workflows/nodes.py::build_update_nodes
                      │                          ├──> core.gate（AIGC 门禁）
                      │                          └──> core.ai（triage LLM，经既有 _decide）
                      └──> core.db.get_pending_updates（仅 sync 扇出端点做发现）
```

- **依赖方向单向**：`server → workflows → core`；`core` 永不 import `workflows`（现状保持）。
- **契约面（改名必须三方同步）**：
  1. `UpdateState` 字段名（§4.2，与 ARCHITECTURE §3.3 同级的硬契约）；
  2. `Hub.update_single` 签名（§3.2）；
  3. `wait_action` 取值 `publish|verify|next`（M2 路由契约沿用，update 图中 `verify` 不可达但取值保留）；
  4. `runner.start/get/list/resume` 的 `kind` 参数（`'publish'|'update'`，老数据默认 `'publish'`）；
  5. `/runs` 系列响应 schema（§6）。
- **浏览器/登录边界**：图节点**只准**经 `Hub._with_adapter`（由 `update_single` 内部调用）触碰浏览器——per-key 互斥、`browser_thread_run` 专属线程、登录态 check/保鲜四层保障全部在该层继承，图层禁止出现任何 playwright 直调（硬约束 a 的落实点）。
- **未来可能变化的边界**（现在不做）：sync 扇出若要严格串行，收敛点在 runner（加 update 并发闸）而非端点；refresh 若触发重评条件，新增 kind 与图；门禁若升级为显式 update 闸门 API，替换 `compliance_gate` 节点实现不动拓扑。

### 2.3 技术选型表

| 层 | 选择 | 备选 | 权衡 |
|---|---|---|---|
| 编排引擎 | 复用 langgraph 1.2.12（已锁版），新增一张图 | 自研线程状态机 / 复用 legacy for 循环加装饰 | 零新依赖满足约束 c；checkpoint/interrupt 免费继承。自研=重造 P2/P3 解药 |
| 图组织 | 独立 `build_update_graph` + 独立 `UpdateState`（同在既有四件套文件内） | 单张多操作大图（op 路由）/ 每操作一图一文件 | 见 §7 对比；同文件内新增保持 §6 目录结构不变 |
| 状态模型 | 新 `UpdateState`（字段名与 `PublishState` 对齐） | 扩展 `PublishState` 加 op 字段 | 见 §4.1，核心考量：不污染已生产验证的 publish 契约 |
| run 元数据 | `workflow_runs` 加 `kind` 列（默认 publish） | 新表 `update_runs` / thread_id 前缀区分 | 单表+过滤最省；新表分裂 list/resume；前缀不可见于 SQL 且老数据迁移 |
| 端点切流 | 新增 `*/workflow` 端点，legacy 端点原样 | legacy 端点内部静默切流 | 与 publish 同款，回退=客户端改回旧路径，行为可见可控 |
| MCP 切流 | 同步轮询 run 至终态（同 publish_article 模式，deadline 放宽） | 工具直接返回 run_id 改为异步契约 | 保持 13 工具既有"返回结果"语义，agent 生态零适配 |

### 2.4 与 legacy 的行为差异（实施时如实标注，均为知情决策）

| # | 差异 | 理由 |
|---|---|---|
| D1 | 标题为空 → run fatal 拒绝更新 | B19 预检对齐 publish（legacy 会照推空标题，属缺陷非特性） |
| D2 | 更新前过 AIGC 门禁（安全扫描+双模型审查；AI 源以 draft_only=True 语义豁免层4） | ADR-009，堵"AI 改写→sync 直推平台"的高危词缺口 |
| D3 | 失败自动分诊重试（上限 `workflow.retry_limit`，默认 2） | P2 修复 |
| D4 | 登录失效/风控 → run 挂起等人工，恢复后续跑 | P3 修复 |
| D5 | 异步 run 契约（run_id 轮询）替代同步返回 results | 长任务防超时 |
| D6 | 支持 `dry_run` 预演（legacy update 无） | ADR-005 沿用，冒烟必需 |

**保持不变**：目标实例过滤逻辑（`platforms` 入参 ∩ `post_id or edit_url`）、平台间风控间隔 `delay_article(30,90)`（最后一个不等，B12 语义）、成功翻转 `publications.status='ok'`、失败仅记 `last_error` 不翻 status（pending 保持，下次 sync 仍能发现）、`jobs` 记账、**不收敛 `articles.status`**（update 不改变文章 published 状态）。

---

## 3. 图拓扑与节点清单

### 3.1 update 图拓扑

```
START
  → load_article       [确定性] 载入文章 + 标题预检（空→fatal→aggregate）
  → compliance_gate    [确定性] AIGC 闸门（dry_run 跳过；拒绝→fatal→aggregate）
  → next_target        [路由头] platforms_queue 弹一个；空→aggregate
  → ensure_login       [确定性] 平台合法性预检（失败→triage 记失败）
  → update_instance    [确定性] Hub.update_single（外包 legacy update 循环体）；dry_run 合成结果
  → triage             [LLM]    成功→next_target；失败→分诊 retry/human/skip
      ├─ retry   (attempts<上限) → update_instance（回边）
      ├─ human   → wait_human [interrupt 挂起等人] →(恢复后)→ update_instance | next_target
      └─ skip/done                → next_target
  → aggregate          [确定性] 收敛 summary + 写 run 摘要（不翻 articles.status）
END
```

与 publish 图（ARCHITECTURE §3.1）逐节点对照的拓扑差异：**无 verify_publish**（更新后内容一致性校验无可靠信号——标题不变、正文比对需拉全文，成本高收益低；失败信号来自 `ad.update` 本身抛错）；**门禁节点参数不同**（§8 ADR-009）；**循环单元是平台级发布实例**而非新发平台。

目标实例发现在 `runner.start(kind='update')` 内**同步预检**（与文章存在性检查同级）：查 `publications` → 按 `platforms` 入参过滤 → 要求 `post_id or edit_url` → 无目标直接 `raise ValueError('没有已发布实例可更新，先 publish')`（视同**启动失败**，走回退规则，见 §6.4）。因此图内**没有** `load_targets` 节点，队列由 start 写入初始 state。

### 3.2 节点清单：复用 / 新增矩阵

| 图内节点名 | 实现 | 来源 | 说明 |
|---|---|---|---|
| `load_article` | **复用**（同一函数对象） | `build_nodes` 内 | 载入 + 标题非空预检，行为与 publish 完全一致 |
| `compliance_gate` | **新增** `compliance_gate_update` | 新写 ~10 行 | 调 `core.gate.apply_gate_before_publish(article, draft_only=True)`；dry_run 返回 `{'passed': True, 'dry_run': True}`；`GateError → fatal`。draft_only=True 语义见 ADR-009 |
| `next_target` | **新增**（镜像 `next_platform`） | 新写 | 弹队列 + 从 `target_pubs` 取当前实例行写 `current_pub` + `attempts` 归零 |
| `ensure_login` | **复用**（同一函数对象） | `build_nodes` 内 | 读 `current_platform` 做 `get_adapter` 预检，跨图语义相同 |
| `update_instance` | **新增**（镜像 `publish_platform`） | 新写 | dry_run 合成 `{platform, ok, dry_run, status:'ok'}`；否则调 `hub.update_single(...)`，异常收进 `current_result.error` |
| `wait_human` | **复用**（同一函数对象） | `build_nodes` 内 | update 语境 `current_result.status` 恒 ≠ `pending_human` → case 恒为 `recover`（故障排除→attempts 归零→`wait_action='publish'`）；`draft_confirm` 分支在本图不可达，**保留不动**以共享实现 |
| `triage` | **决策核心复用 + 收尾新写** `triage_update` | `_decide` / `_llm_triage` / 三组错误词典 / `TRIAGE_SYSTEM` / `_retry_limit` 均为 nodes.py 模块级，直接复用 | 成功路径恒 `finish({ok…})`（update 无 pending_human）；失败路径与 publish 同构；target 间 sleep 用 `hub.delay_article`（30,90，legacy update 同款；publish 用 delay_platform 是 publish legacy 同款——各图守各 legacy 的行为） |
| `aggregate` | **新增** `aggregate_update` | 新写 | summary 形状对齐 publish：`{fatal, dry_run, targets_total, targets_ok, ok, failed:[{platform, error}]}`；**不含** `pending_human` 列、**不翻转** `articles.status` |

**Hub 侧新增原语**：

```python
def update_single(self, article_id, platform, pub, article, account="default"):
    """原地更新单个平台实例并完成落库（jobs/publications 记账）。

    legacy update() 循环体与工作流节点 update_instance 共用的唯一更新原语
    （对称于 publish_single）。pub 携带 post_id/edit_url。
    成功返回 {'platform', 'ok': True}；失败在完成失败记账后抛异常。"""
```

抽取原则：**逐行搬移** legacy `update()` 循环体（`core/service.py:594-613`），仅去掉循环与 sleep（sleep 留在 legacy 循环/triage 各自的编排层）；`_with_adapter` 调用原样 → per-key 互斥、浏览器线程、登录保鲜自动继承。legacy `update()` 改为循环调 `update_single`，行为逐字不变。

### 3.3 路由表（update 图条件边）

| 源节点 | 路由函数 | 分支键 → 目标 |
|---|---|---|
| `load_article` | `_route_after_load`（复用） | `fatal → aggregate`；否则 `→ compliance_gate` |
| `compliance_gate` | `_route_after_gate_update` | `fatal → aggregate`；否则 `→ next_target` |
| `next_target` | `_route_after_next_target` | `current_platform=='' → aggregate`；否则 `→ ensure_login` |
| `ensure_login` | `_route_after_login`（复用） | 预检失败 `→ triage`；否则 `→ update_instance` |
| `triage` | `_route_after_triage_update` | `ok → next_target`；`decisions[-1].action==retry → update_instance`；`human → wait_human`；否则 `→ next_target` |
| `wait_human` | `_route_after_wait_update` | `wait_action: publish → update_instance`；`next → next_target`（`verify` 不可达，缺省落 `next_target`） |
| `aggregate` | 硬边 | `→ END` |

### 3.4 sync 扇出时序（编排层，无图）

```
POST /sync/pending/workflow
  │ 同步段（毫秒级）：
  │  1. get_pending_updates() → 按 article_id 分组（与 legacy 同 SQL）
  │  2. 每组 runner.start(kind='update', platforms=组内平台集)
  │     └ start 内预检：文章存在？目标实例非空？→ ValueError 即该篇启动失败
  │  3. 返回所有 run_id
  └→ 无 pending → {count: 0, runs: []}（不建 run，非错误）

后台：各 run 独立线程并行推进（同平台跨 run 由 per-key 互斥串行、跨平台 ≤ POOL_MAX=4，
     与并发 publish run 的既有限流机制完全相同——见风险 R5 知情说明）
```

---

## 4. 状态模型（字段级）

### 4.1 裁定：新建 `UpdateState`，不扩展 `PublishState`

| 选项 | 一致性 | 回滚速度 | 维护成本 | 结论 |
|---|---|---|---|---|
| 扩展 `PublishState`（加 `op`/`current_pub` 等） | 表面高，实际低——update 无意义字段（`draft_only`）、publish 无意义字段（`current_pub`）混居一室，节点必须处处判 op，字段语义漂移风险最高 | 差：改动了 M1–M3 已生产验证的契约（ARCHITECTURE §3.3 是"逐字硬契约"），回滚要连 publish 一起回 | 高：单 State 双语义，每个节点内 if-op | 否 |
| **新建 `UpdateState`（选定）** | 同名字段跨 State 语义**强制一致**（§4.3 契约规则），差异字段各自独立、零歧义 | 好：`PublishState` 一个字符不动，update 图删除即整体回退 | 中：两份 TypedDict，但同名字段代码模式相同，节点函数可直接复用 | **是** |

TypedDict 是结构型（非名义型），LangGraph StateGraph 各绑各的 State 是标准用法；`PublishState` 已是 ARCHITECTURE §3.3 逐字契约，M5 不得污染。

### 4.2 `UpdateState` 字段签名（属性名逐字，加进 `workflows/state.py`）

```python
class UpdateState(TypedDict, total=False):
    # —— 运行标识与入参（与 PublishState 同名同义）——
    run_id: str                 # workflow_runs.id
    article_id: int
    account: str
    dry_run: bool               # 预演模式：不触真实平台，合成结果（ADR-005 语义沿用）

    # —— 编排游标 ——
    platforms_queue: list       # 待更新平台队列（next_target 弹出；start() 按目标实例建队）
    current_platform: str       # 当前平台（'' = 队列已空）
    current_pub: dict           # 当前平台的发布实例行 {platform, post_id, edit_url, account}
    target_pubs: dict           # platform → 实例行（start() 一次性写入，next_target 查表用）
    attempts: int               # 当前平台已尝试次数（update_instance 递增）

    # —— 中间产物 ——
    article: dict               # 载入并经闸门修正后的文章
    gate: dict                  # 闸门结果 {'passed': bool, ...}
    current_result: dict        # 当前平台最近一次尝试结果（覆盖语义）

    # —— 累积产物（追加语义，Annotated[list, operator.add]）——
    results: Annotated[list, operator.add]     # 每平台终态 {platform, ok, status?, error?, attempts?, note?}
    decisions: Annotated[list, operator.add]   # 分诊决策留痕 {platform, error, attempts, action, reason, by, ts}

    # —— 异常与收尾 ——
    fatal: str                  # 引擎级终止原因（文章缺失/标题为空/闸门拒绝）
    human_resume: dict          # wait_human 恢复时人的输入 {'approved', 'note'}
    wait_action: str            # wait_human 恢复去向: publish|next（verify 取值保留但本图不可达）
    summary: dict               # aggregate 收敛（runner 落库 result_json.summary）
```

**初始 state（`runner.start` 写入）**：
`{'run_id', 'article_id', 'account', 'dry_run', 'platforms_queue': [平台名...], 'target_pubs': {平台: 实例行}, 'results': [], 'decisions': []}`

### 4.3 与 `PublishState` 对照 + 契约规则

| 字段 | PublishState | UpdateState | 规则 |
|---|---|---|---|
| `run_id / article_id / account / dry_run / article / gate / current_result / platforms_queue / current_platform / attempts / results / decisions / fatal / human_resume / wait_action / summary` | 有 | 有 | **同名必同义**：reducer、类型、语义跨两 State 一致；`wait_action` 取值集合统一 `publish|verify|next` |
| `draft_only` | 有 | **无** | update 无草稿概念 |
| `current_pub` / `target_pubs` | **无** | 有 | update 需要实例行（post_id/edit_url 是原地更新的钥匙） |
| `gate` | 有 | 有 | 语义同（门禁结果），但 UpdateState 的 gate 来自 `draft_only=True` 调用（ADR-009） |

字段名是跨节点/runner/API 的硬契约：**改名必须同步 ARCHITECTURE.md §3.3/§3.5 与所有节点**（state.py 顶部注释沿用此警告）。

---

## 5. runner 与存储扩展

### 5.1 `WorkflowRunner` kind 泛化（backend 实施要点）

```python
# __init__：单图 → 双图字典（checkpointer 共用同一 SqliteSaver）
self.graphs = {
    'publish': build_graph(hub, checkpointer=self.saver),
    'update':  build_update_graph(hub, checkpointer=self.saver),
}

def start(self, article_id, platforms=None, account='default',
          draft_only=False, dry_run=False, kind='publish'):
    # kind='update' 分支：
    #   - 忽略 draft_only
    #   - platforms=None 表示"全部可更新实例"
    #   - 同步预检：文章存在（ValueError→404）；
    #     目标实例 = get_publications ∩ platforms ∩ (post_id or edit_url)
    #     为空 → ValueError('没有已发布实例可更新，先 publish')  # 视同启动失败
    #   - meta 行写 kind 列；初始 state 见 §4.2

def list(self, limit=50, kind=None, article_id=None):   # 新增过滤，均可选
# get()/resume()：按 meta 行 kind 选 self.graphs[kind]（老数据 kind 缺省 'publish'）
# _spawn：按 kind 取图；thread_id 仍 = run_id（两图 checkpoint 靠 kind 路由取对图，run_id 全局 uuid 无碰撞）
```

`resume` 与 `start` 的图选择必须来自**同一 meta 行 kind**——这是防"用 publish 图读 update checkpoint"的唯一闸门，backend 必须在 `resume` 入口读 row 并选图，禁止猜测。

### 5.2 workflow.db 迁移（ADR-004 不破：仍全在 `data/workflow.db`）

```sql
-- runner.__init__ 内，幂等包裹 try/except（重复执行无害）
ALTER TABLE workflow_runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'publish';
CREATE INDEX IF NOT EXISTS idx_runs_kind ON workflow_runs(kind, created_at DESC);
```

- `DEFAULT 'publish'` 使**存量行**读出即 `publish`，老 run 的 get/resume/list 零迁移；
- `hub.db` **一个字节不动**（d) 约束 + ADR-004）；
- 备份要求不变：双 db 文件同备（ARCHITECTURE §7 已有条目，devops 知会即可）。

### 5.3 线程与并发模型

- 沿用：每 run 一个后台 daemon 线程；meta/checkpoint 双连接 `check_same_thread=False + timeout=30`；同 run 串行；
- 浏览器限流沿用：`POOL_MAX=4` + per-key 互斥 + `browser_thread_run` 单线程（不新增任何并发原语）；
- sync 扇出= 同步毫秒级起 N 个 run 后立即返回，**不引入**扇出级并发闸（现有限流兜底；严格串行是 M6 备选，见 R5）。

---

## 6. 接口清单（交 api-designer）

### 6.1 新增端点

**① `POST /articles/{aid}/update/workflow`**

```jsonc
// Request
{ "platforms": ["csdn","zhihu"] | null,   // null/缺省 = 全部可更新实例
  "account": "default",
  "dry_run": false }
// Response 200（立即返回）
{ "run_id": "abc123def456", "status": "running", "poll": "/runs/abc123def456" }
// 错误
// 404  {"detail": "文章 {aid} 不存在"}
// 409  {"detail": "工作流引擎已通过 config workflow.enabled=false 禁用"}
// 422  {"detail": "没有已发布实例可更新，先 publish"}   // 启动预检失败，未建 run
```

**② `POST /sync/pending/workflow`**

```jsonc
// Request
{ "account": "default", "dry_run": false }
// Response 200（立即返回；count=0 表示无待同步，非错误、未建 run）
{ "count": 2,
  "runs": [ { "article_id": 3, "title": "…", "run_id": "a1…" },
            { "article_id": 7, "title": "…", "run_id": "b2…" } ] }
// 错误：409（同上，引擎禁用且未启动任何 run）
```

> **评审确认 2026-09-22（architect，经主理人中转）**：sync 响应允许 additive `failed[]`（api-designer 决策 D-C）——区分「无 pending」与「全启动失败」，MCP 回退判定（run_ids 空才回退）依赖该字段；本节响应形状以含 `failed[]` 为准。

### 6.2 修改端点（向后兼容）

**③ `GET /runs`**：新增可选 query `kind=publish|update`、`article_id=int`；`limit` 不变。响应数组每项**新增** `kind` 字段，其余字段（`id/article_id/title/platforms/status/error/dry_run/human_task/summary/created_at/updated_at`）不变。缺省不过滤 = 返回全部（老客户端无感）。

**④ `GET /runs/{run_id}`**：响应**新增** `kind`；`checkpoint` 结构不变（`node` 可能出现 `next_target`/`update_instance` 等新节点名——前端运行详情按字符串展示，无需改动）。

**⑤ `POST /runs/{run_id}/resume`**：**契约零变化** `{"approved": true, "note": ""}` → `{"run_id", "status":"running"}`；服务端按 kind 路由到对应图恢复。错误语义沿用（409 非 waiting_human / 执行中）。

### 6.3 保留不动（legacy 回退路径，硬约束 b）

`POST /articles/{aid}/update`（同步，返回 `results` 或 `{skipped}`）、`POST /sync/pending`（同步分组结果）、`GET /refresh/{platform}`（**永久保留**，§1.4 裁定）。三者行为逐字不变，仅建议加 strangler 注释区分主/备路径。

### 6.4 MCP 工具契约变更（交 backend-engineer，非 api-designer）

**`update_article`** 切流（逐款照抄 `publish_article` 已验证模式）：
```
start = _runner().start(id, platforms, kind='update')
  └ 异常且 run_id is None → 回退 hub.update(id, platforms)   # 仅启动失败回退（含 422 无目标→legacy 返回 {skipped}，契约完美对齐）
轮询 deadline = 900s（update 平台间隔是 delay_article 30–90s，publish 的 300s 不够用）
  ├ done          → {"run_id", "results": result.results}
  ├ waiting_human → results + [{platform, ok:true, warning: human_task.message, edit_url}]  # 同 publish 模式
  ├ failed        → results（缺失则按 platforms 合成失败行）
  └ 超时（run 仍在跑）→ raise TimeoutError（带 run_id 提示；run_id is not None 绝不回退，防双发）
```

**`sync_pending`** 切流：发现分组 + 逐篇 `start(kind='update')` → 轮询**全部** run 至终态（deadline 900s）→ 组装 legacy 形状 `[{article_id, title, platforms, result}]` 并附 `run_ids` 与 `failed`（HTTP `failed[]` 原样透传——部分启动时被丢的篇目及原因必须让 agent 看见）。**回退判定**：`len(runs)==0`（一篇都没启动成功，**failed 非空也回退**——无 run 即无双发，回退后 legacy 重新发现）才回退 `hub.sync_pending()`；非空则超时/异常一律 raise 带 run_ids，绝不回退。

**`refresh_platform`**：**不切流**，保持 `hub.refresh` 直调（§1.4 裁定）。

---

## 7. 备选方案与代价对比

**方案 A（选定）**：独立 `UpdateState` + update 专图 + runner `kind` 路由；sync=编排层扇出复用 update 图；refresh 不接入。

**方案 B（否）**：单张多操作大图——把 publish 图改造为 `op ∈ {publish, update}` 条件路由的统一图，State 扩展为混合大 State，节点内判 op 分支。

**方案 C（否）**：全量三图独立——update 图、sync 独立跨文章图、refresh 图，各自 State/runner 通道。

| 维度 | 方案 A（选定） | 方案 B 单图多操作 | 方案 C 三图全接 |
|---|---|---|---|
| **一致性** | 中高：同名字段跨 State 强制同义、决策核心（`_decide`）与 wait_human 同一份实现；两图拓扑各守各 legacy 行为 | **表面最高实则最低**：op 分支渗入每个节点（gate/verify/target 差异全靠 if-op），单 State 内 draft_only 与 current_pub 互斥字段混居，语义漂移面最大 | **最低**：三图三 State，节点复制（triage/wait_human 若不同文件即漂移），与 legacy 行为对齐要对三处 |
| **回滚速度** | **最快**：`PublishState`/publish 图零改动；回退=API/MCP 切回 legacy + 删 kind 路由，update 图整文件弃用 | **最慢**：动了已生产验证的 publish 图本体，回退=重写 publish 拓扑并重新 E2E（掘金真实挂起场景重验） | 快（各图独立弃），但 refresh/sync 接入本身制造了三处需要回退的点 |
| **维护成本** | 中：2 图 + runner 小改 + 双 State 契约表；同步扇出只是端点 20 行 | **最高**：一张图养两种语义，新增第三操作继续膨胀；每加字段先问"哪个 op 用" | **最高**：3 图×（State+节点+路由）+ sync 跨文章 State 要发明多文章队列/多 article_id 模型 + refresh 图纯负债 |
| 侵入面 | 仅 runner/meta 加列、api 加 2 端点、MCP 改 2 工具 | 触碰 publish 主路径（R1 风险升 H 的根源） | 全面铺开，工作量 3 倍于 A |
| 一致性/legacy 对账 | 单点（update_single 抽取） | 双点且 publish 点已被污染 | 三点 |
| 符合硬约束 | a~e 全满足 | 威胁 b（publish 回退变重） | 威胁 c（无新依赖满足，但 YAGNI 违背 d 的"沿用"精神） |

**选定理由**：A 在三维度均为"次优以上 + 无致命短板"，B 输在回滚速度与维护成本（且回滚恰恰是硬约束 b 的核心），C 输在为无价值操作（refresh/sync 独立图）付出结构性成本。

---

## 8. 关键 ADR（背景/选项/决定/后果）

### ADR-007：update 用独立图 + 独立 State + runner kind 路由
- **背景**：update 接入不能污染 M1–M3 生产验证的 publish 资产（state/graph/runner 单通道）。
- **选项**：独立图+State（A）/ 单图 op 路由（B）/ 扩展 PublishState 共图。
- **决定**：A。`workflow_runs` 加 `kind` 列路由图，thread_id 不变。
- **后果**：+1 图维护面、meta 迁移一次；−publish 零风险、回退解耦；两 State 同名字段须契约表守护（R7）。

### ADR-008：sync_pending 编排层扇出（一文一 run）；refresh 不接入
- **背景**：sync 无独立节点语义；refresh 无引擎价值点。
- **选项**：扇出复用（选定）/ sync 独立跨文章图 / sync 也不同步改走 legacy 永留。
- **决定**：sync 端点与 MCP 工具承担发现+扇出，一文一 run；refresh 永久 legacy 并写死重评触发条件。
- **后果**：run 列表天然是"每篇文章更新史"；跨文章全局进度由客户端聚合（count+run_ids 已给足）；sync 扇出并发风控知情接受（R5）；AUDIT 遗留表 update/sync 行可勾销、refresh 行改"经评估不接入"。

### ADR-009：update 合规门禁——gate 进图，`draft_only=True` 豁免层4，保留层1+层3
- **背景**：legacy update 无门禁；`ai_rewrite → sync` 能把 AI 改写内容直推**线上**实例，高危词/审查拒绝的内容经 update 路径裸奔（既存合规缺口，publish 路径没有）。
- **选项**：① 不设门禁（legacy parity，缺口延续）；② 全量门禁 `draft_only=False`（AI 源文章更新**全部**被拒，堵死 ai_rewrite→sync 流程，体验倒退）；③ **选定**：`apply_gate_before_publish(article, draft_only=True)`——层1 内容安全扫描 + 层3 双模型审查照跑（`GateError → fatal`，run 失败不开浏览器），层4"AI 源须 draft_only"以 draft_only=True 豁免。
- **决定**：③。理由：层4 的人审对象是"**新内容首次上线**"；update 的对象是曾经过闸发布的实例，增量审查由层1+层3 承担；AI 源更新内容经 `add_aigc_label` 幂等补标识后推平台，反而强化法规"显式标识"。dry_run 跳过门禁（与 publish 同）。
- **后果**：+更新耗时增加一次本地/LLM 审查（publish 同款，可接受）；+层4 在 update 语境弱化是**知情决策**（AI 触发的 MCP sync 依赖层1+层3 兜底）；如后续要恢复层4，把节点参数改 `draft_only=False` 并给 AI 源加 update 专用人工确认（wait_human 第三场景）即可，拓扑不动。

---

## 9. 风险表（3×3 矩阵定级）

**定级矩阵**（行=概率，列=影响）：

| 概率 \ 影响 | 高 | 中 | 低 |
|---|---|---|---|
| **高** | H | H | M |
| **中** | H | M | L |
| **低** | M | L | L |

| # | 风险 | 概率 | 影响 | 级 | 缓解 |
|---|---|---|---|---|---|
| R1 | runner kind 波及 publish 生产路径（`start/_spawn/resume/get` 共享代码改造引入回归） | 中 | 高 | **H** | kind 缺省 `'publish'`；publish 分支代码路径逐字保留；**验收门禁：`smoke_workflow` + `smoke_hitl` 7 断言 + 真实掘金 dry_run 复跑全绿才算过**；/publish 端点行为不变断言 |
| R2 | MCP update/sync 切流后轮询超时（`delay_article` 30–90s×N 平台，publish 的 300s deadline 必超） | 高 | 中 | **H** | deadline 放宽 900s；超时 raise 必带 run_id；"绝不回退防双发"规则写进工具 docstring；文档注明多平台 sync 属长任务 |
| R3 | `update_single` 抽取走样（记账/status 翻转与 legacy 不一致 → publications 错账、pending 死循环或丢失） | 中 | 高 | **H** | 逐行搬移 legacy 循环体（对照 publish_single 已验证模式）；冒烟加"同场景 legacy vs 引擎双跑 DB 状态 diff 断言"；抽回退=legacy update() 原样恢复 |
| R4 | 双路径并发双更新（切流期 legacy 端点与 workflow 同文同平台并发） | 中 | 中 | M | per-key 互斥保证**串行**不并发；update 幂等（覆盖写同内容），危害=重复耗时+风控暴露；切流文档标注禁双调；启动后不回退规则不变 |
| R5 | sync 扇出 N run 并行 → 同平台跨文章背靠背更新，30–90s 文章间隔被互斥排队抹平 | 中 | 中 | M | 知情接受（与并发 publish run 同暴露面，POOL_MAX+互斥兜底）；runs 结果可审计；M6 备选：runner 级 update 串行闸（收敛点已预留 §2.2） |
| R6 | workflow.db 迁移失败（ADD COLUMN/索引）→ 所有 run 启动失败（含 publish） | 低 | 高 | M | 幂等 try/except；runner 启动自检（迁移失败打 error 日志并拒绝服务新端点，legacy 不受影响）；兜底=停服删 workflow.db 重建（checkpoint 可弃，hub.db 无恙） |
| R7 | `UpdateState`/`PublishState` 同名字段语义漂移（如 wait_action 取值、results 条目形状） | 中 | 中 | M | §4.3 契约表写进两文件头注释；ARCHITECTURE §3.5 回写对照表；前端/审计消费的 summary 形状冒烟断言 |
| R8 | 门禁入图误拒（REVIEW_MODEL 二审误判 reject → 更新被 fatal 拦） | 低 | 中 | L | 未配 REVIEW_MODEL 时走本地 heuristic（确定性、误拒面小）；fatal 错误详情在 run.error 可见；必要时 `AIGC_GATE:false` 急关（既有开关） |
| R9 | refresh"不接入"裁定被执行者推翻、重复评估/顺手接图 | 低 | 低 | L | §1.4 写死重评触发条件；AUDIT 遗留表改注"经评估不接入（M5 裁定）" |
| R10 | `wait_human` 的 draft_confirm 分支在 update 图不可达，维护者误读为死代码而"清理" | 低 | 低 | L | 节点与 graph.py 注释双处标注"共享实现，update 图恒走 recover" |

**H 项为实施阶段每日盯防对象；R1/R3 是合并门禁（冒烟不过=不合并）。**

---

## 10. 实施顺序与冒烟验收（backend-engineer 编码清单）

按序实施，每步独立可验：

1. **[refactor] 抽取 `Hub.update_single`**：legacy `update()` 循环改调它，行为逐字不变（py_compile + 手测 legacy 端点）。
2. **[engine] `workflows/state.py` 加 `UpdateState`**（§4.2 逐字）；`nodes.py` 加 `build_update_nodes(hub)`（§3.2 矩阵）；`graph.py` 加 `build_update_graph`（§3.1/3.3）。
3. **[engine] `runner.py` kind 泛化 + schema 迁移**（§5.1/5.2，注意 resume 按 meta 行选图）。
4. **[api] 两个新端点 + `/runs` 过滤**（§6.1/6.2；复用 `_workflow_enabled()` 409 语义）。
5. **[mcp] `update_article`/`sync_pending` 切流**（§6.4，照抄 publish_article 防双发结构）。
6. **冒烟（验收门禁）**：
   - S1 dry_run update 双平台：图跑通、results 全 ok、run 落库 `kind=update`、**legacy `/update` 行为不变**；
   - S2 重试回边：注入失败桩，attempts 达 `retry_limit` 停、decisions 留痕 `by=heuristic`；
   - S3 门禁 fatal：高危词文章 dry_run=False 启动 → run failed、**不开浏览器**、error 含门禁原因；
   - S4 recover 挂起→恢复：失败桩触发 triage→human→run waiting_human→`POST /runs/{id}/resume`→回 update_instance→done（复用 smoke_hitl 模式）；
   - S5 sync 扇出：造 2 篇 pending → dry_run → count=2、两 run 全 done、pending 清零；
   - S6 R1/R3 回归门禁：`smoke_workflow` + `smoke_hitl` 全绿 + legacy/引擎双跑 DB diff 断言。
7. **[docs] 回写**：ARCHITECTURE §3.1/3.5 增 update 图与状态表、ADR-007~009、§5 M5 行、Changelog 0.3.4；AUDIT 遗留表勾销 update/sync、改注 refresh 裁定；本文件状态改"已定稿"。

**明确不做（YAGNI 边界）**：前端新 UI（挂起卡片/运行记录按 run 通用展示，update run 自动出现）；sync 并发闸；update 的 verify 节点；门禁第三场景；任何新依赖。

---

## 11. 移交要点

- **→ api-designer**：只新增 §6.1 两端点、修改 §6.2 三端点（加字段/参数，严格向后兼容）；§6.3 三端点冻结；错误码语义 404/409/422 分工见各 schema 注释；`/runs` 新响应字段 `kind` 请同步 OpenAPI 描述。
- **→ database-engineer**：唯一 DDL=`workflow_runs` 加列+索引（§5.2，幂等、只动 workflow.db）；hub.db 零改动；备份清单确认双 db；无需为 refresh/sync 建任何新表。
- **→ backend-engineer**：按 §10 七步走，R1/R3 冒烟不过不合并；`update_single` 抽取与 kind 选图（resume 必读 meta 行）是两个最易错点；MCP deadline 900s 别照抄 300s。

## 12. 硬约束自检

| 约束 | 满足方式 |
|---|---|
| a) 登录态四层 + 共享驱动/browser_thread_run | 设计零触碰 browser 层；节点仅经 `_with_adapter`（update_single 内）碰浏览器，互斥/单线程/保鲜全继承（§2.2 边界规则） |
| b) legacy 保留 + 仅启动失败回退、启动后绝不回退 | §6.3 三端点冻结；§6.4 MCP 回退判定=run_id/run_ids 为空；超时 raise 带 run_id |
| c) 无新依赖；workflow.db 独立 | 只用 langgraph 1.2.12 既有 API（StateGraph/interrupt/SqliteSaver）；全部改动落 `data/workflow.db`（§5.2） |
| d) M2 机制沿用 | wait_human interrupt/resume 原样复用；triage heuristic 兜底+LLM 复用 `_decide`；decisions append 留痕同款（§3.2） |
| e) 本阶段只设计不改码 | 本文档为唯一产出，未改任何业务代码 |
