# -*- coding: utf-8 -*-
"""REST API：AI 或你自己的脚本通过这个管整个中台。

已深度合并进新的 FastAPI 后端：本模块导出 ``hub_router``（APIRouter）与
``register_hub(app)``，由 ``app/factory.py`` 在 ``backed/start.py`` 统一装配；
同时保留 ``app`` 以便独立运行（``python -m api.hub`` / ``uvicorn api.hub:app``）。
"""

import json
import os
import time
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.publishing import observability as obs

ROOT = Path(__file__).resolve().parent.parent


# ---------------- 惰性单例 ----------------
_hub_instance = None
_task_manager = None


def get_hub():
    """惰性创建 Hub 实例，避免模块导入时产生副作用。"""
    global _hub_instance
    if _hub_instance is None:
        from service.publishing.service import Hub
        _hub_instance = Hub(headless=True)
    return _hub_instance


def get_task_manager():
    """惰性创建 TaskManager 单例。"""
    global _task_manager
    if _task_manager is None:
        from service.publishing.tasks import TaskManager
        from service.publishing import db
        _task_manager = TaskManager(get_hub(), db.connect())
    return _task_manager


hub_router = APIRouter()


# ---------------- 可选 API 鉴权 ----------------
# config.json 里配 "api_token": "一串随机字符串" 即启用：
# 非信任来源的所有请求，必须带 X-API-Token 头。默认不配 = 不启用（本地用）。
# 信任来源：本机回环 / testclient / 信任网段（可经环境变量 TRUSTED_NETS 追加 CIDR）。
def _api_token():
    try:
        return (json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
                or {}).get("api_token") or ""
    except Exception:
        return ""


def _trusted_sources():
    """本机回环 + 测试客户端 + 配置的信任网段（CIDR）。"""
    nets = ["127.0.0.0/8", "::1/128"]
    extra = os.environ.get("TRUSTED_NETS", "").strip()
    if extra:
        nets += [n.strip() for n in extra.split(",") if n.strip()]
    return nets


def _client_ip(request):
    """反代感知取真实客户端 IP：优先 X-Forwarded-For 首个，回退到直连 host。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        try:
            return ip_address(first)
        except ValueError:
            pass
    host = request.client.host if request.client else ""
    if host:
        try:
            return ip_address(host)
        except ValueError:
            pass
    return None


def _is_trusted(request):
    ip = _client_ip(request)
    if ip is None:
        return False
    for net in _trusted_sources():
        try:
            if ip in ip_network(net, strict=False):
                return True
        except Exception:
            continue
    return False


def _attach_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _auth(request, call_next):
        token = _api_token()
        if token and not _is_trusted(request) \
                and request.headers.get("X-API-Token") != token:
            return JSONResponse({"detail": "无效的 API Token"}, status_code=401)
        return await call_next(request)

    # ---------------- 可观测性：结构化 access log + 指标 ----------------
    # 每个 API 请求落一条 JSON 行到 data/observability/events.log，
    # 带 method/path/status/duration/client_ip，排障时直接 grep 链路。
    # /metrics 自身不记录（避免指标端点把日志刷爆）。
    _LOG_SKIP = ("/metrics", "/health", "/docs", "/openapi.json", "/redoc")

    @app.middleware("http")
    async def _access_log(request, call_next):
        t0 = time.time()
        resp = await call_next(request)
        dur = round(time.time() - t0, 3)
        path = request.url.path
        if not any(path.startswith(s) for s in _LOG_SKIP):
            status = getattr(resp, "status_code", 0)
            ok = 200 <= status < 400
            obs.METRICS.incr(f"api.{ 'ok' if ok else 'fail' }")
            obs.METRICS.observe("api.dur", dur)
            obs.METRICS.incr(f"api.{request.method.lower()}.hits")
            obs.emit("api.access",
                     method=request.method, path=path, status=status,
                     duration=dur,
                     client_ip=(request.client.host if request.client else ""))
        return resp


# ---------------- CORS（默认仅同源；跨域部署时用环境变量 CORS_ORIGINS 白名单） ----------------
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]


class ArticleIn(BaseModel):
    title: str
    content_md: str = ""
    summary: str = ""
    tags: str = ""
    cover: str = ""
    status: str = "draft"
    source: str = "human"   # AI 写稿时由 service 显式传 ai，别默认标成 AI
    ai_model: str = ""


class ArticlePatch(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[str] = None
    cover: Optional[str] = None
    status: Optional[str] = None


class PublishIn(BaseModel):
    platforms: List[str]
    account: str = "default"
    draft_only: bool = False
    live: bool = False      # true=附带实时预览页（异步端点专用）
    settings: Optional[Dict[str, Dict]] = None  # 平台特有字段：{平台id: {category, tags}}


class UpdateIn(BaseModel):
    platforms: Optional[List[str]] = None   # None/缺省 = 全部可更新实例
    account: str = "default"


class ResumeIn(BaseModel):
    approved: bool = True
    note: str = ""


class ImportIn(BaseModel):
    path: str
    tags: str = ""


class AIWriteIn(BaseModel):
    topic: str
    style: str = ""
    words: int = 2000
    tags_hint: str = ""
    publish_to: Optional[List[str]] = None
    model: str = ""           # "provider:model_name" 或 "model_name"
    preferred_provider: str = ""


class AIRewriteIn(BaseModel):
    instruction: str
    publish_to: Optional[List[str]] = None
    model: str = ""
    preferred_provider: str = ""


class AIModelIn(BaseModel):
    model: str = ""           # "provider:model_name" 或 "model_name"
    preferred_provider: str = ""


@hub_router.get("/status")
def status():
    return get_hub().status()


# ---------------- 文章 ----------------

@hub_router.get("/articles")
def list_articles(status: str = None, limit: int = 100):
    return get_hub().list(status, limit)


@hub_router.post("/articles")
def create_article(a: ArticleIn):
    return {"id": get_hub().create(**a.dict())}


@hub_router.get("/articles/{aid}")
def get_article(aid: int):
    r = get_hub().get(aid)
    if not r:
        raise HTTPException(404, "文章不存在")
    return r


@hub_router.put("/articles/{aid}")
def update_article(aid: int, patch: ArticlePatch):
    data = {k: v for k, v in patch.dict().items() if v is not None}
    ok, pending = get_hub().edit(aid, **data)
    return {"ok": ok, "pending_sync": pending}


@hub_router.get("/articles/search/{keyword}")
def search(keyword: str):
    return get_hub().search(keyword)


@hub_router.post("/articles/import")
def import_md(body: ImportIn):
    return {"id": get_hub().import_md(body.path, tags=body.tags)}


# ---------------- 发布 / 更新 / 同步（统一任务引擎语义，重构第一刀） ----------------
# 三套入口（legacy 同步 / async / workflow）合并为一套：提交任务 → 返回 task_id →
# 轮询 GET /tasks/{task_id}。AI/无人值守与 Web 前端走同一条路，不再有回退分支。

@hub_router.post("/articles/{aid}/publish")
def publish(aid: int, body: PublishIn):
    """异步发布：提交到统一任务引擎，立即返回 task_id，轮询 GET /tasks/{task_id}。"""
    task_id = get_hub().tasks.submit("publish", article_id=aid, platforms=body.platforms,
                               account=body.account, draft_only=body.draft_only,
                               settings=body.settings)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/articles/{aid}/update")
def update(aid: int, body: UpdateIn):
    """异步原地更新：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = get_hub().tasks.submit("update", article_id=aid, platforms=body.platforms,
                               account=body.account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/sync/pending")
def sync_pending(body: Optional[UpdateIn] = None):
    """异步同步扇出：把所有待更新实例提交一个 sync 任务，引擎内部分组执行。"""
    account = body.account if body else "default"
    task_id = get_hub().tasks.submit("sync", account=account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


# ---------------- 统一任务查询 / 恢复 ----------------

@hub_router.get("/tasks")
def tasks_list(limit: int = 50, kind: str = None, status: str = None):
    """任务列表（替代原 /runs）：按 kind/status 过滤，默认返回最近 50 条。"""
    return get_hub().tasks.list(limit=limit, kind=kind, status=status)


@hub_router.get("/tasks/{task_id}")
def tasks_detail(task_id: str):
    """查询任意任务状态：pending / running / ok / failed / waiting_human。"""
    t = get_hub().tasks.get(task_id)
    if not t:
        raise HTTPException(404, "任务不存在或已过期")
    t = dict(t)
    try:
        t["result"] = json.loads(t.get("result") or "{}")
    except Exception:
        t["result"] = {}
    try:
        t["platforms"] = json.loads(t.get("platforms") or "[]")
    except Exception:
        t["platforms"] = []
    return t


@hub_router.post("/tasks/{task_id}/resume")
def tasks_resume(task_id: str, body: Optional[ResumeIn] = None):
    """恢复 waiting_human 任务：approved=true 重新执行；false 标记放弃。"""
    approved = body.approved if body else True
    r = get_hub().tasks.resume(task_id, approved=approved)
    if not r.get("ok"):
        raise HTTPException(409, r.get("error", "恢复失败"))
    return r


@hub_router.get("/pending-human")
def pending_human():
    """需要人工处理的发布实例（如掘金草稿等人点"确定并发布"）。
    前端轮询这个端点做角标提醒；点"去处理"直接打开草稿编辑页。"""
    rows = get_hub().conn.execute(
        """SELECT p.article_id, a.title, p.platform, p.account, p.edit_url,
                  p.post_id, p.updated_at
           FROM publications p LEFT JOIN articles a ON a.id = p.article_id
           WHERE p.status = 'pending_human'
           ORDER BY p.updated_at DESC""").fetchall()
    return [dict(r) for r in rows]


@hub_router.get("/publications")
def publications(article_id: int = None, platform: str = None):
    sql = ("SELECT p.*, a.title FROM publications p "
           "LEFT JOIN articles a ON a.id = p.article_id WHERE 1=1")
    args = []
    if article_id is not None:
        sql += " AND p.article_id=?"
        args.append(article_id)
    if platform is not None:
        sql += " AND p.platform=?"
        args.append(platform)
    sql += " ORDER BY p.updated_at DESC"
    return [dict(r) for r in get_hub().conn.execute(sql, args).fetchall()]


# ---------------- 账号 / 平台 ----------------

@hub_router.get("/platforms")
def platforms():
    from service.publishing.adapters.base import ADAPTERS
    return [{"id": a.id, "name": a.name, "needs_browser": a.needs_browser}
            for a in ADAPTERS.values()]


@hub_router.get("/accounts")
def accounts():
    return get_hub().accounts()


@hub_router.get("/accounts/{platform}/check")
def check_account(platform: str, account: str = "default"):
    return {"platform": platform, "logined": get_hub().check(platform, account)}


class LoginIn(BaseModel):
    account: str = "default"
    timeout: int = 600
    # handoff=弹验证码就暂停交人工（默认）；abort=无人值守时直接放弃
    on_captcha: str = "handoff"


@hub_router.post("/accounts/{platform}/login")
def login(platform: str, body: LoginIn):
    """异步启动登录：提交任务，轮询 GET /tasks/{task_id}。
    引擎会开有头浏览器去平台登录页等扫码，登录态落盘后任务结束；
    遇验证码默认 handoff 交人工（无人值守可传 on_captcha=abort）。"""
    task_id = get_hub().tasks.submit("login", platforms=[platform], account=body.account)
    return {"task_id": task_id, "platform": platform, "status": "pending",
            "poll": f"/tasks/{task_id}"}


@hub_router.delete("/accounts/{platform}")
def logout(platform: str):
    """清除登录态：删 profile + cookie 快照，账号状态置离线。"""
    r = get_hub().logout(platform)
    return {"ok": True, **r}


@hub_router.get("/accounts/{platform}/diagnose")
def diagnose(platform: str):
    """这个平台该怎么接、验证码怎么过——排查用。"""
    return get_hub().diagnose(platform)


class CaptchaIn(BaseModel):
    account: str = "default"
    wait: int = 180


@hub_router.post("/accounts/{platform}/solve-captcha")
def solve_captcha(platform: str, body: CaptchaIn):
    """打开页面就地处理验证码：先半自动试，不行转人工。"""
    return get_hub().solve_captcha(platform, body.account, body.wait)


class AssistIn(BaseModel):
    url: str
    timeout: int = 900


@hub_router.post("/accounts/{platform}/assist")
def assist_open(platform: str, body: AssistIn):
    """带登录态的内置有头浏览器打开平台页（人工步骤接管），提交任务轮询结果。"""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url 必须是 http(s) 地址")
    task_id = get_hub().tasks.submit("assist", platforms=[platform], url=body.url)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/refresh/{platform}")
def refresh(platform: str, limit: int = 50):
    """异步抓取平台文章入库：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = get_hub().tasks.submit("refresh", platforms=[platform])
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


# ---------------- AI 写稿 ----------------

@hub_router.post("/ai/write")
def ai_write(body: AIWriteIn):
    return get_hub().ai_write(body.topic, body.style, body.words,
                        body.tags_hint, body.publish_to,
                        model=body.model or None,
                        preferred_provider=body.preferred_provider or None)


@hub_router.post("/articles/{aid}/ai-rewrite")
def ai_rewrite(aid: int, body: AIRewriteIn):
    return get_hub().ai_rewrite(aid, body.instruction, body.publish_to,
                               model=body.model or None,
                               preferred_provider=body.preferred_provider or None)


@hub_router.post("/articles/{aid}/ai-polish")
def ai_polish(aid: int, body: AIModelIn = None):
    model = body.model if body else None
    preferred = body.preferred_provider if body else None
    return get_hub().ai_polish(aid, model=model, preferred_provider=preferred)


@hub_router.get("/ai/status")
def ai_status():
    ready = get_hub().ai_ready()
    providers = []
    try:
        from service.publishing import providers as prov_mod
        providers = prov_mod.list_providers()
    except Exception:
        pass
    return {"ready": ready, "providers": providers}


@hub_router.get("/ai/providers")
def ai_providers():
    """列出所有可用 Provider + 模型（前端下拉菜单）。"""
    from service.publishing import providers as prov_mod
    return prov_mod.list_providers()


@hub_router.get("/ai/gate")
def ai_gate():
    """AIGC 合规门禁状态：开关、审查模型、高危词数、最近拒绝。"""
    from service.publishing import gate as g
    snap = {"enabled": g.is_enabled(),
            "review_model": g._cfg("REVIEW_MODEL", "").strip() or "(未配置，走本地 heuristic)",
            "dangerous_terms": len(g.DANGEROUS_PATTERNS),
            "human_review_gate": "AI 源内容禁止直接 publish，须 draft_only + 人工确认"}
    try:
        rows = get_hub().conn.execute(
            "SELECT * FROM jobs WHERE type='publish' AND status='failed' "
            "ORDER BY id DESC LIMIT 50").fetchall()
        denied = [dict(r) for r in rows if any(
            k in (r["message"] or "") for k in ("门禁", "高危", "人工确认", "合规"))]
        snap["recent_denied"] = denied[:10]
    except Exception:
        snap["recent_denied"] = []
    return snap


@hub_router.get("/jobs")
def jobs(limit: int = 50):
    from service.publishing import db
    return [dict(r) for r in db.list_jobs(get_hub().conn, limit)]


# ==================== 定时发布调度器 ====================

class ScheduleIn(BaseModel):
    article_id: int
    platforms: List[str]
    account: str = "default"
    draft_only: bool = False
    schedule_type: str = "once"        # once/daily/weekly/cron
    schedule_expr: str = ""            # 表达式
    title: str = ""


class SchedulePatch(BaseModel):
    title: Optional[str] = None
    platforms: Optional[List[str]] = None
    account: Optional[str] = None
    draft_only: Optional[bool] = None
    schedule_type: Optional[str] = None
    schedule_expr: Optional[str] = None
    enabled: Optional[bool] = None


@hub_router.get("/schedules")
def schedules_list(include_disabled: bool = False):
    return get_hub().scheduler.list_all(include_disabled=include_disabled)


@hub_router.post("/schedules")
def schedules_create(body: ScheduleIn):
    sid = get_hub().scheduler.create(
        body.article_id, body.platforms, body.account, body.draft_only,
        body.schedule_type, body.schedule_expr, body.title)
    return {"id": sid, **get_hub().scheduler.get(sid)}


@hub_router.get("/schedules/{sid}")
def schedules_get(sid: int):
    s = get_hub().scheduler.get(sid)
    if not s:
        raise HTTPException(404, "定时任务不存在")
    return s


@hub_router.put("/schedules/{sid}")
def schedules_update(sid: int, body: SchedulePatch):
    data = {k: v for k, v in body.dict().items() if v is not None}
    ok = get_hub().scheduler.update(sid, **data)
    return {"ok": ok, **get_hub().scheduler.get(sid)}


@hub_router.post("/schedules/{sid}/pause")
def schedules_pause(sid: int):
    return get_hub().scheduler.pause(sid)


@hub_router.post("/schedules/{sid}/resume")
def schedules_resume(sid: int):
    return get_hub().scheduler.resume(sid)


@hub_router.post("/schedules/{sid}/trigger")
def schedules_trigger(sid: int):
    """手动立即触发一次（不改调度计划）。"""
    return get_hub().scheduler.trigger_now(sid)


@hub_router.delete("/schedules/{sid}")
def schedules_delete(sid: int):
    return get_hub().scheduler.delete(sid)


# ==================== 文章版本历史 ====================

@hub_router.get("/articles/{aid}/versions")
def versions_list(aid: int, limit: int = 50):
    from service.publishing.versions import list_versions
    return list_versions(get_hub().conn, aid, limit=limit)


@hub_router.get("/articles/{aid}/versions/{vid}")
def versions_get(aid: int, vid: int):
    from service.publishing.versions import get_version
    v = get_version(get_hub().conn, vid)
    if not v:
        raise HTTPException(404, "版本不存在")
    return v


@hub_router.get("/articles/{aid}/versions/diff")
def versions_diff(aid: int, v1: int, v2: int):
    """对比两个版本的差异。"""
    from service.publishing.versions import diff_versions
    return diff_versions(get_hub().conn, v1, v2)


@hub_router.post("/articles/{aid}/versions/{vid}/rollback")
def versions_rollback(aid: int, vid: int):
    """回滚文章到指定版本。"""
    from service.publishing.versions import rollback
    ok, msg = rollback(get_hub().conn, vid)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ==================== AI 增强工具 ====================

@hub_router.post("/articles/{aid}/ai-translate")
def ai_translate(aid: int, body: AIModelIn = None, target_lang: str = "en"):
    """翻译文章到目标语言。target_lang: en/ja/ko/fr/de。"""
    model = body.model if body else None
    preferred = body.preferred_provider if body else None
    return get_hub().ai_translate(aid, target_lang, model=model,
                                  preferred_provider=preferred)


@hub_router.get("/articles/{aid}/ai-image-prompts")
def ai_image_prompts(aid: int, n: int = 3, model: str = None,
                     preferred_provider: str = None):
    """根据文章内容生成文生图 prompt。"""
    return get_hub().ai_image_prompts(aid, n, model=model,
                                       preferred_provider=preferred_provider)


@hub_router.get("/articles/{aid}/ai-outline")
def ai_outline(aid: int):
    """提炼文章大纲。"""
    return get_hub().ai_outline(aid)


@hub_router.get("/articles/{aid}/ai-seo")
def ai_seo(aid: int):
    """生成 SEO 元数据。"""
    return get_hub().ai_seo(aid)


@hub_router.post("/articles/{aid}/clone")
def article_clone(aid: int):
    """克隆文章。返回新文章 ID。"""
    return get_hub().clone(aid)


@hub_router.get("/ai/templates")
def ai_templates():
    """列出所有可用写作模板。"""
    return get_hub().list_ai_templates()


@hub_router.post("/ai/write-template")
def ai_write_template(
    topic: str, template: str = "", style: str = "",
    words: int = 2000, tags_hint: str = ""
):
    """用预置模板 AI 写文章。"""
    art = get_hub().ai_write_with_template(
        topic, template, style=style, words=words, tags_hint=tags_hint)
    aid = get_hub().create(art["title"], art["content_md"],
                           summary=art["summary"], tags=art["tags"],
                           source="ai", ai_model=art.get("ai_model", ""))
    return {"id": aid, "title": art["title"], "summary": art["summary"]}


# ==================== 内容质检 ====================

@hub_router.post("/articles/{aid}/qa")
def article_qa(aid: int):
    """对已有文章运行完整质检（可读性 + SEO + 重复度）。"""
    return get_hub().content_qa(article_id=aid)


@hub_router.post("/qa/analyze")
def qa_analyze(content_md: str, title: str = "", summary: str = "", tags: str = ""):
    """对任意文本运行质检（不保存文章）。"""
    return get_hub().content_qa(content_md=content_md, title=title,
                                summary=summary, tags=tags)


# ==================== 标签治理 ====================

@hub_router.get("/tags")
def tags_list(limit: int = 50, category: str = None):
    from service.publishing.tags import list_tags
    return list_tags(get_hub().conn, limit=limit, category=category or None)


@hub_router.get("/tags/trending")
def tags_trending(limit: int = 10):
    from service.publishing.tags import trending
    return trending(get_hub().conn, limit=limit)


@hub_router.post("/tags/sync")
def tags_sync():
    """从 articles 重建标签统计。"""
    from service.publishing.tags import sync_from_articles
    return sync_from_articles(get_hub().conn)


@hub_router.post("/tags/rename")
def tags_rename(old: str, new: str):
    from service.publishing.tags import rename_tag
    return rename_tag(get_hub().conn, old, new)


@hub_router.post("/tags/merge")
def tags_merge(_from: str = "", to: str = ""):
    """合并标签：_from -> to（_from 被合并消失，to 保留）。"""
    from service.publishing.tags import merge_tags
    if not _from or not to:
        raise HTTPException(422, "from 和 to 必填")
    return merge_tags(get_hub().conn, _from, to)


@hub_router.post("/tags/alias")
def tags_alias(alias: str = "", canonical: str = ""):
    """添加标签别名：alias 出现时自动替换成 canonical。"""
    from service.publishing.tags import add_alias
    if not alias or not canonical:
        raise HTTPException(422, "alias 和 canonical 必填")
    return add_alias(get_hub().conn, alias, canonical)


@hub_router.post("/tags/suggest")
def tags_suggest(title: str = "", content_md: str = ""):
    """根据标题+正文推荐 3-5 个标签。"""
    from service.publishing.tags import suggest_for_article
    return {"tags": suggest_for_article(get_hub().conn, title or "", content_md or "")}


# ---------------- 可观测性端点 ----------------

# ==================== Webhook / 事件 ====================

class WebhookIn(BaseModel):
    url: str
    secret: str = ""
    events: Optional[List[str]] = None   # None=["*"] 表示全订阅
    enabled: bool = True


@hub_router.get("/webhooks")
def webhooks_list():
    from service.publishing import events as evt_mod
    return evt_mod.list_webhooks()


@hub_router.post("/webhooks")
def webhooks_create(body: WebhookIn):
    from service.publishing import events as evt_mod
    wid = evt_mod.register_webhook(body.url, body.events, body.secret, body.enabled)
    return {"id": wid, "message": "Webhook 注册成功"}


@hub_router.put("/webhooks/{wid}")
def webhooks_update(wid: int, body: WebhookIn):
    from service.publishing import events as evt_mod
    data = {k: v for k, v in body.dict().items() if v is not None}
    ok = evt_mod.update_webhook(wid, **data)
    if not ok:
        raise HTTPException(404, "Webhook 不存在")
    return {"ok": True}


@hub_router.delete("/webhooks/{wid}")
def webhooks_delete(wid: int):
    from service.publishing import events as evt_mod
    ok = evt_mod.delete_webhook(wid)
    if not ok:
        raise HTTPException(404, "Webhook 不存在")
    return {"ok": True}


@hub_router.post("/webhooks/{wid}/test")
def webhooks_test(wid: int):
    """发送测试事件到指定 webhook。"""
    from service.publishing import events as evt_mod
    evt_mod.init_events()
    evt_mod.emit("test", {"message": "Content Harbor 测试事件", "webhook_id": wid})
    return {"ok": True, "message": "测试事件已派发"}


@hub_router.get("/notifications")
def notifications_list(since: float = None, limit: int = 50):
    """获取最近站内通知（事件环形缓冲）。"""
    from service.publishing import events as evt_mod
    return evt_mod.get_notifications(since=since, limit=limit)


@hub_router.get("/metrics")
def metrics():
    """实时指标快照：计数器 + 耗时直方图 + 事件计数。

    重启归零；长期趋势看 jobs 表 + events.log（grep trace_id 串联链路）。
    """
    snap = obs.METRICS.snapshot()
    snap["events_log"] = str(obs.EVENT_LOG)
    snap["trace_hint"] = "发布/更新链路 grep 'trace' + trace_id 于 events.log"
    return snap


def register_hub(app: FastAPI) -> None:
    """把平台发布 REST API 挂载进（新的）FastAPI 应用。

    - 主后端 ``app/factory.py`` 调用本函数即完成"把 server/api.py 合并进新后端"
    """
    app.include_router(hub_router, prefix="/api/hub")


# ---------------- 独立运行入口 ----------------
app = FastAPI(title="AI 内容中台", version="0.2.0")
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
register_hub(app)
