# 内容港 Harbor

> [English](README.en.md) · 中文

> **内容进港，全网分发。** 文章存在你自己的库里，AI 通过 REST API 全权管理：写、改、发、更新、看账号全部内容。
> 自带内置浏览器（Patchright 反检测 fork），扫码登录一次就长期在线，不依赖你日常的 Chrome / Edge 开着。

<p>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="fastapi" src="https://img.shields.io/badge/API-FastAPI-teal">
  <img alt="platforms" src="https://img.shields.io/badge/platforms-10-blueviolet">
  <img alt="GitCode" src="https://img.shields.io/badge/GitCode-badhope%2Fcontent--harbor-1a73e8">
  <img alt="国内模型" src="https://img.shields.io/badge/AI-DeepSeek%20%2F%20豆包%20%2F%20通义-brightgreen">
</p>

![内容港 · 主界面（晴空主题）](docs/screenshots/01-home.png "写作视图：文章列表 + 分屏编辑器")

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/02-editor.png" alt="编辑器"><br><sub>Markdown 编辑 / 分屏 / 预览三态，写完直接选平台发</sub></td>
    <td width="50%"><img src="docs/screenshots/03-publish.png" alt="发布向导"><br><sub>一键多发，发布实例落库，可原地更新已发文章</sub></td>
  </tr>
</table>

> **v0.4.0 重构**：后端已收敛到 `backed/`（FastAPI + SQLite + 统一任务引擎）。
> 旧 scaffold（`core/database` / `core/cache` / `core/queue` / `models` / `schemas` / `repository` 等）已全部拆除，
> 代码精简到 115 个文件，编译通过、沙箱内 10 个适配器全部实测运行通过。
> 开发规范见 [`AGENT.md`](AGENT.md)，架构说明见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

## 30 秒看懂它能干什么

- **多平台一键分发**：一篇文章，勾选平台，同时发到 **10 个平台**（掘金 / CSDN / 博客园 / 知乎 / 思否 / B站专栏 / 头条号 / 开源中国 / 51CTO / 自建博客）。
- **原地更新，不是重发**：改了文章，它去打开各平台的**编辑页**改原文，URL 不变、评论点赞都在。
- **AI 全权接管**：REST API — Claude / Cursor / 任意脚本都能直接建文章、发布、抓取账号里的文章。
- **完全自托管**：文章库、登录态、浏览器 profile 全在你自己的机器上，不依赖任何第三方 SaaS。
- **免扫码通道**：博客园 / 51CTO / 自建博客走 MetaWeblog 协议，账号密码直发，一次配置长期免登录。
- **自带 Web 管理界面**：明亮清爽的「晴空」主题，响应式适配桌面 / 平板 / 手机。

## 快速开始（后端 · FastAPI）

后端位于 `backed/`，基于 FastAPI，默认 SQLite、零外部依赖即可启动；生产可切 MySQL / PostgreSQL。

```bash
# 本地启动（仅依赖 uv，跨平台）
./start.sh          # Linux / macOS
start.bat           # Windows cmd
start.ps1           # PowerShell
# 或手动：
cd backed && uv sync && uv run uvicorn app.factory:create_app --host 0.0.0.0 --port 8000 --reload
```

- API 文档：http://localhost:8000/docs
- 部署：见 `deploy/`（docker-compose + Dockerfile + Nginx 反代）

### CLI 常用命令（在 `backed/` 目录下运行）

```bash
cd backed
uv run python cli.py status                             # 中台总览
uv run python cli.py serve                              # 起 REST 服务（默认 http://127.0.0.1:8800）
```

> REST 端点（含发布 / 原地更新 / 同步 / AI / 账号）见 `backed/api/hub.py`，发布引擎见
> `backed/service/publishing/`，统一任务引擎见 `backed/service/publishing/tasks.py`。

## 支持平台（10 个）

| 平台 | 方式 | 发布 | 原地更新 | 抓取列表 | 备注 |
|---|---|---|---|---|---|
| 掘金 | 浏览器 + 页面 API | ✅ | ✅ | ✅ | 实测真发成功 |
| CSDN | 浏览器 | ✅ | ✅ | ✅ | 验证码登录 |
| 博客园 | MetaWeblog 协议 | ✅ | ✅ | ✅ | **免浏览器、零验证码** |
| 51CTO | MetaWeblog 账密 | ✅ | ✅ | ✅ | 免扫码，账号密码直发 |
| 自建博客 | MetaWeblog 账密 | ✅ | ✅ | ✅ | WordPress/Typecho，免扫码 |
| 知乎 | 浏览器 UI 注入 | ✅ | ✅ | — | 扫码登录 |
| 思否 SegmentFault | 浏览器 UI | ✅ | ✅ | — | |
| B站专栏 | 浏览器 UI | ✅ | ✅ | — | |
| 头条号 | 浏览器 UI | ✅ | — | — | |
| 开源中国 | 浏览器 UI | ✅ | — | — | |

> 知乎 / 头条 / 开源中国的适配器参考社区实测（MultiPost-Extension 等），平台改版后
> 直接扩一个新平台照着任一适配器抄 150 行。

## 这是什么 / 不是什么

- ✅ 是：**自托管**的多平台内容分发中台。文章库、发布、原地更新、AI 写稿，全部在你自己机器上。
- ✅ 是：给 AI / 脚本用的**内容 API**。REST API 接口简洁，Claude / Cursor / 任意脚本都能直接调用。
- ❌ 不是：群发垃圾内容的工具。发布内置限速（平台间隔 8-20s、文章间隔 30-90s），请在平台规则内使用。

---

## 一、为什么不用浏览器插件方案

| | 插件方案（Wechatsync 等） | 本方案（内置浏览器） |
|---|---|---|
| 登录态 | 寄生在你日常浏览器里 | 独立 profile 存本地，程序自己管 |
| 浏览器关了 | 断，跑不了 | 后台常驻，定时任务照跑 |
| 编辑已发布文章 | ❌ 接口层面就没有 | ✅ 打开编辑页原地改 |
| AI 全权管理 | 只能"发" | 增删改查 + 列表 + 状态 |
| 做成独立程序 | 做不到，必须寄生 | 天然独立，能打包分发 |

代价：平台适配要自己写。目前 10 个平台已实现（见上方平台矩阵），
扩平台照着 150 行抄一个即可。文章可以由 AI 直接写（`backed/service/publishing/ai.py`），接任何 OpenAI 兼容模型（DeepSeek / 豆包 / 通义 / Kimi / 智谱 / Ollama）。

---

## 二、架构

```
        AI（Claude / 你的脚本）
             │  REST API
             ▼
   ┌──────────────────────┐
   │      业务层 service   │  ← FastAPI 路由 (api/hub.py)
   ├──────────────────────┤
   │  文章库 articles      │  唯一真源，AI 写/改都在这儿
   │  发布实例 publications │  文章×平台，存 post_id / edit_url
   │  任务引擎 tasks       │  统一串行队列，DB 持久化不丢
   └──────────┬───────────┘
              │
     内置 Chromium（每平台一个持久化 profile，Patchright 反检测）
              │
     适配器：掘金 / CSDN / 知乎 / 思否 / B站 / 头条 / 开源中国 / 博客园 / 51CTO / 自建博客(WordPress/Typecho)
              │
     发布    列表    原地更新
```

**原地更新靠三件事**：发布时把 `post_id` 和 `edit_url` 存进 `publications`；列表时从 DOM 抓 `edit_url`（不猜 URL）；改文章时自动把已发布实例标成 `pending`，`sync` 一把推平。

**任务引擎**：所有长任务（发布/更新/登录/同步/抓取）统一走 SQLite 持久化队列，单线程串行消费（浏览器是全局单实例），失败分诊确定性规则（验证码→转人工、网络抖动→自动重试 3 次、其余→判失败留 error）。进程重启不丢任务，`waiting_human` 可恢复。

---

## 三、命令行用法

> CLI 入口在 `backed/cli.py`；以下命令请在 `backed/` 目录下执行

```bash
# 1) 导入一篇文章
python cli.py import-md --path ./my-post.md

# 2) 发布
python cli.py publish --id 1 --platforms juejin,csdn

# 3) 改文章 → 自动同步到所有已发平台（原地更新，不是新发一篇）
python cli.py update --id 1
# 或者一把推平所有改动
python cli.py sync

# 看看账号里已有什么
python cli.py refresh --platform juejin
python cli.py status
```

---

## 四、Web 管理界面

先把前端构建一次（`cd web && pnpm install && pnpm build`），产物落在 `web/dist/`，
由后端挂载到根路径。启动后端后浏览器打开 `http://127.0.0.1:8000`。

界面走「**晴空**」主题——明亮现代 SaaS 风：浅灰底 + 纯白卡片 + 飞书蓝主色，
圆角适中、系统字体栈（零外部请求）、全链路离线可用，顶栏是分组工具条
（品牌 / AI 状态 / 主操作），编辑器为绝对主角。

**前端技术栈**（`web/` 目录，独立工程）：

| 项 | 选型 | 为什么 |
|---|---|---|
| 框架 | Vue 3 `<script setup>` | 组合式 API，逻辑按功能聚在一处 |
| UI 库 | Element Plus（**按需引入**） | 只打包用到的组件，CSS 从 379KB 降到 148KB |
| 状态 | Pinia | 文章、发布实例、平台、统计分域管理 |
| 请求 | axios + 拦截器 | 统一错误提示，不用每个调用点写 try/catch |
| 渲染 | md-editor-v3 | 编辑/分屏/预览三态，代码块和表格都对 |
| 构建 | Vite 6 | 秒级热更新，产物按 vue / element / md 分包 |

**响应式适配**（窗口一变自动重排，不是简单的媒体查询隐藏）：

| 宽度 | 布局 | 交互 |
|---|---|---|
| ≥1280 | 两栏常驻（列表+编辑） | 全展开 |
| 768–1280 | 两栏（列表+编辑） | 列表收起为顶部按钮 |
| <768 | 单栏（仅编辑区） | 列表 → 左侧抽屉；工具条换行，按钮只留图标 |

**开发 / 构建**：

```bash
cd web
pnpm install
pnpm dev        # 开发模式，:5173，自动代理 /api 到后端（默认 :8000）
pnpm build      # 构建到 server/static/（vite.config.js 决定），后端挂载此目录
```

---

## 五、让 AI 直接写

```bash
export AI_API_KEY=sk-xxx                       # 或写进 .env
export AI_BASE_URL=https://api.deepseek.com/v1 # 通义/豆包/Kimi/智谱/本地 Ollama 都行
export AI_MODEL=deepseek-chat

# 通过 REST API 写一篇文章
curl -X POST http://localhost:8000/ai/write \
  -H 'Content-Type: application/json' \
  -d '{"topic":"怎么用 AI 管内容中台","words":2000}'

# 写完直接发
curl -X POST http://localhost:8000/articles/1/publish \
  -H 'Content-Type: application/json' \
  -d '{"platforms":["juejin","cnblogs"]}'
```

AI 写完自动抽标题、生成摘要和 3-5 个标签，直接入库。改写/润色之后，
已发布的实例会自动标成待同步——`sync` 一把就推到各平台去。

---

## 六、REST API 端点

服务启动后（默认 `http://127.0.0.1:8000`），提供以下端点：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/status` | 总览 |
| GET | `/platforms` | 已实现平台列表 |
| GET/POST | `/articles` | 列表 / 新建 |
| GET/PUT | `/articles/{id}` | 读 / 改 |
| POST | `/articles/{id}/publish` | 发布（返回 `task_id`，异步轮询） |
| POST | `/articles/{id}/update` | **原地更新**（返回 `task_id`） |
| POST | `/sync/pending` | 推平所有改动（返回 `task_id`） |
| POST | `/refresh/{platform}` | 抓账号文章入库（返回 `task_id`） |
| GET | `/publications` | 发布实例列表 |
| GET | `/pending-human` | 需要人工处理的实例 |
| GET/POST | `/tasks` | 任务列表 / 过滤 |
| GET | `/tasks/{task_id}` | 任务详情与结果 |
| POST | `/tasks/{task_id}/resume` | 恢复 waiting_human 任务 |
| GET | `/accounts`、`/accounts/{platform}/check` | 账号状态 |
| POST | `/accounts/{platform}/login` | 扫码登录 |
| GET | `/accounts/{platform}/diagnose` | 平台接入诊断 |
| POST | `/accounts/{platform}/solve-captcha` | 半自动过验证码 |
| POST | `/accounts/{platform}/assist` | 有头浏览器人造接管 |
| POST | `/ai/write` | AI 写一篇并入库 |
| POST | `/articles/{id}/ai-rewrite` | AI 改写 |
| POST | `/articles/{id}/ai-polish` | AI 润色 |
| GET | `/ai/status`、`/ai/gate` | AI / AIGC 合规门禁状态 |
| GET | `/metrics` | 实时指标快照 |

交互式 API 文档：http://localhost:8000/docs

> 所有长任务（发布/更新/同步/登录/抓取）均返回 `task_id`，前端 / 脚本通过轮询
> `GET /tasks/{task_id}` 获取进度：`pending` → `running` → `ok` / `failed` / `waiting_human`。

---

## 七、验证码与人机识别：三层策略

先把话说清楚：**"绕过验证码"这个说法本身是个坑**。

阿里云、极验、腾讯那类验证码，判定逻辑在服务端，前端 JS 加密后上报鼠标轨迹/环境指纹。
网上那些"破解"仓库（逆向滑块距离、训练模型识别缺口）的共同问题是：
平台一次风控升级就全部失效，而且账号被标记后**直接封**，代价远大于收益。

所以本项目的做法是三层递进——**想办法不遇到 > 遇到一次就永久解决 > 真遇到了交人工**：

### L1 能走官方通道就不模拟浏览器（最彻底）

有的平台开放了协议接口，压根不会有验证码。这是首选。

| 平台 | 通道 | 验证码 |
|---|---|---|
| 博客园 | MetaWeblog XML-RPC + 访问令牌 | **零验证码** |
| 51CTO | MetaWeblog 账密 | **零验证码** |
| 自建博客 | MetaWeblog 账密 | **零验证码** |
| 掘金 | 有页面 API | 部分走 API |
| CSDN / 知乎 / 头条 / 开源中国 / B站 / 思否 | 无公开发布 API，只能浏览器 | 走 L2/L3 |

### L2 反检测 + 登录态持久化（降低触发率）

`backed/service/publishing/browser.py` 使用 **Patchright**（Playwright 反检测 fork），
配合自研反检测脚本逐条抹平自动化痕迹：

| 指纹点 | 处理 |
|---|---|
| `navigator.webdriver` | 删除，并清掉原型链上的 |
| WebGL vendor/renderer | 伪装成 `Intel Inc. / Intel Iris OpenGL Engine` |
| 硬件参数 | `hardwareConcurrency`/`deviceMemory` 补成 8 |
| 插件 / 语言 | 补 5 个插件、`zh-CN,zh,en` |
| `window.chrome` | 补上（真 Chrome 有，Playwright 没有） |
| `outerHeight` | 修正（无头下等于 inner，是破绽） |
| 启动参数 | `--disable-blink-features=AutomationControlled` 等 |
| 输入行为 | 逐字符输入 + 打错退格；鼠标走贝塞尔弧线 + 抖动 + 末段减速 |

配合 **登录态持久化**：一次登录存进 `backed/data/profiles/<平台>_<账号>/`，
之后复用，把"过验证"从每天一次压到一次性。

### L3 半自动 + 人工交接（真弹了怎么办）

`backed/service/publishing/humanize.py` + `CaptchaPolicy`：

1. **先半自动试一次** —— 纯复选框那种（"确认您不是机器人"）经常能过。
   滑块会试着按变速轨迹拖过去。
2. **过不了就转人工** —— 此时浏览器窗口已经开着，你直接在里面点/拖/选。
   代码每 2 秒轮询一次，验证码消失就自动接着往下跑。同时自动截图 +
   存 HTML 到 `data/captcha/`，方便你看现场。
3. **顺手再试** —— 人工等待期间每 20 秒重试一次半自动（有的验证码会刷新，重试能过）。

### 无人值守怎么办

验证码天然需要人。要真无人值守，只有两条路：

1. **优先用 L1**：能走协议的平台（博客园 / 51CTO / 自建博客）就根本不碰验证码
2. **定期保活**：登录态是有有效期的。写个定时任务每周跑一次 check，
   掉线了发通知给你，你花 1 分钟手动补一次

### 关于 xvfb（Linux 部署必看）

有头浏览器需要 X Server。服务器/容器里没有，程序会**自动拉一个 Xvfb**。
没装的话：

```bash
apt install -y xvfb
```

---

## 八、博客园配置（推荐新手第一个接通）

博客园走 MetaWeblog 协议最稳、零验证码。需要协议三件套：
`endpoint`（XML-RPC 地址）/ 登录用户名 / 访问令牌。

登录博客园后台 → 设置 → 其他设置 → MetaWeblog → 记下这三件套，
写入 `config.json`：

```json
{
  "platforms": {
    "cnblogs": {
      "endpoint": "https://www.cnblogs.com/你的blogApp/services/metaweblog.aspx",
      "username": "你的登录用户名",
      "token": "从后台复制的访问令牌"
    }
  }
}
```

以后发博客园就走纯协议，**不开浏览器、不过验证码**。

> ⚠️ 别把数字用户 ID 当登录用户名。登录名是注册时那个（邮箱 / 手机号 / 自定义用户名）。

---

## 九、两种适配器，挑着用

**浏览器型**（掘金、CSDN 等）：开内置 Chromium 操作编辑器，通用但慢，受页面改版影响。

**协议型**（博客园 / 51CTO / 自建博客）：走 MetaWeblog XML-RPC，**不开浏览器**，
稳定一个数量级，登录态不过期。适配器里设 `needs_browser = False`，
中台会自动跳过浏览器那一步。看到哪个平台有开放 API，优先写协议型。

## 十、性能与稳定性

- **浏览器实例池**：无头浏览器按平台常驻复用（LRU 上限 4 个），第二次起发布不再付
  1~3 秒的启动开销；页面用完即关、实例保活，浏览器崩溃会自动重建重试一次。
  扫码登录前会自动释放该平台的池实例（profile 目录是独占的，不能两处同时开）。
- **SQLite WAL 模式** + 30s busy_timeout：多线程并发写不再偶发 `database is locked`。
- **可选 API 鉴权**：config.json 里设 `"api_token": "随机串"` 即启用，所有请求需带
  `X-API-Token` 头（默认关闭，本机使用不需要）。服务要暴露到局域网/公网时必须开启。

---

## 十一、扩展新平台（照抄 150 行）

在 `backed/service/publishing/adapters/` 新建 `xxx.py`，实现四个动作：

```python
@register
class XxxAdapter(PlatformAdapter):
    id = "xxx"
    name = "平台名"
    login_url = "..."
    home_url  = "..."   # 登录后才能进的页，判登录态用
    list_url  = "..."
    new_url   = "..."
    needs_browser = True  # False = 纯 API，不走浏览器

    def check_auth(self, page) -> bool: ...
    def list_articles(self, page, limit=50): ...
    def publish(self, page, article, options): ...
    def update(self, page, pub, article) -> bool: ...
```

最后在 `backed/service/publishing/service.py` 里
`from service.publishing.adapters import xxx` 导入一下即可注册。

**校准技巧**：平台改版导致选择器失效时，别瞎猜——

```python
from service.publishing.browser import dump_dom
dump_dom(page, "csdn_list")     # HTML 存到 data/debug/
```

打开存下来的 HTML 搜关键词，真实结构一目了然，比猜快十倍。
平台专属的 URL / API / 选择器全在各适配器顶部常量区，改版了只改那一块。

---

## 十二、当前状态与已知限制

**已跑通（真实账号 + 沙箱实测）**：

| 能力 | 状态 |
|---|---|
| 数据层 / 业务层（文章库、发布实例、统一任务引擎） | ✅ |
| AI 写稿（标题抽取、摘要、标签、改写、润色） | ✅ 接任何 OpenAI 兼容模型 |
| REST API（28+ 端点，OpenAPI 文档自动生成） | ✅ |
| 内置浏览器 + Patchright 反检测（8 项指纹抹平） | ✅ |
| Web 管理界面（晴空主题） | ✅ v0.4.0 重构后编译通过 |
| 响应式适配（桌面 / 平板 / 手机） | ✅ |
| 验证码三层策略 + Xvfb 自动兜底 | ✅ |
| 10 个平台适配器（沙箱全部 import 通过） | ✅ |

**已知限制**：
- 平台风控：程序内置了平台间隔（8-20s）和文章间隔（30-90s）限速
- 数据中心 / 云服务器 IP 容易被平台风控踢登录态，**首次扫码登录建议在家庭/办公网络完成**，登录态持久化后换环境复用
- 单账号模型，`account` 参数已预留但多账号并发未测
- **验证码做不到 100% 自动**：服务端判定的验证码（阿里云/极验/reCAPTCHA）本质上需要人。
  程序的设计目标是"尽量不遇到 + 遇到了一次性解决 + 真弹了交人工"。
  要完全无人值守，走 L1 的协议通道（博客园 / 51CTO / 自建博客的 MetaWeblog）
- **首次登录必须在能看到浏览器的机器上做**：建议在有桌面的机器上一次，
  把 `backed/data/profiles/` 整个拷到服务器复用

---

## 十三、目录结构

```
content-harbor/
├─ backed/                # 后端（FastAPI）：业务层 + 平台适配器 + 发布引擎
│  ├─ app/                # 应用装配 / 中间件 / 路由
│  ├─ api/                # REST 端点（hub.py）
│  ├─ service/publishing/ # 核心：任务引擎 + 10 个平台适配器 + 浏览器
│  │  └─ adapters/        # csdn / juejin / zhihu / bilibili / cnblogs /
│  │                     # oschina / segmentfault / toutiao / wuyi_cto / metaweblog
│  ├─ config/             # 多环境配置
│  ├─ utils/              # 日志 / 异常 / 响应码
│  └─ data/               # SQLite 库 + 浏览器 profiles + captcha 截图
├─ web/                   # 前端（Vue3 + Vite，独立工程）
├─ deploy/                # 部署编排（docker-compose / Dockerfile / Nginx）
├─ docs/                  # 截图 + 文档
├─ start.sh / .bat / .ps1 # 本地启动脚本（仅依赖 uv）
├─ AGENT.md               # 面向 AI 助手的项目说明
└─ README.md              # 本文件
```

---

## 十四、参与贡献

欢迎 Issue / PR。新增平台照着 `adapters/` 下任一文件抄 150 行即可。

## 十五、AI 使用说明（透明度声明）

- 本项目的**产品设计、架构与代码由人工主导完成，AI 辅助编码与测试**；
- 项目自身的定位是"AI 辅助内容创作"工具：文章由 AI 起草、人审核后发布，
  请遵守各平台的 AI 内容规范；
- 请勿将本工具用于批量灌水、刷量等违反平台规则的行为，账号风险自负。

## 仓库地址

| 平台 | 地址 |
|---|---|
| **GitCode（主）** | <https://gitcode.com/badhope/content-harbor> |
| Gitee（国内镜像） | <https://gitee.com/badhope/content-harbor> |
| GitHub（国际镜像） | <https://github.com/X33834/content-harbor-fixed> |

## 许可证

[MIT](LICENSE) © 2026 badhope
