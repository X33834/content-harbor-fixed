# -*- utf-8 -*-
"""事件系统：任务结果 webhook 推送 + 站内通知。

解决什么问题：
  - 发布/更新任务完成后，外部系统无法实时感知（原来只能轮询任务接口）
  - 没有通知中心，前端只靠 30 秒一次的 polling 感知新事件

架构：
  - webhooks 表：注册需要推送的事件类型 + URL + secret
  - 事件触发：TaskManager / Hub 在关键节点 emit() 同步 → 异步派发线程 POST 到 webhook
  - 通知中心：内存环形缓冲（最近 100 条），前端 GET /events 拉取、SSE 实时推送
"""

import hashlib
import hmac
import json
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from pathlib import Path

import sqlite3 as _sql

ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = ROOT / "data" / "hub.db"

# 事件类型 → 说明
EVENT_TYPES = {
    "task.ok": "任务完成",
    "task.failed": "任务失败",
    "task.waiting_human": "任务等待人工",
    "publish.ok": "发布成功",
    "publish.failed": "发布失败",
    "article.created": "新建文章",
    "article.updated": "文章更新",
    "account.login": "登录成功",
    "account.logout": "登出",
    "ai.write": "AI 写稿完成",
    "ai.rewrite": "AI 改写完成",
}

# 站内通知环形缓冲（跨线程安全）
_notifications = deque(maxlen=200)
_notifications_lock = threading.Lock()

# 异步派发队列
_dispatch_q = deque()
_dispatch_cv = threading.Condition()
_dispatcher_running = False


# ---------------- Webhook 存储 ----------------

def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = _sql.connect(str(_DB_PATH), timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def init_events(conn=None):
    """建 webhooks 表（如果还没有）。"""
    c = conn or _conn()
    c.execute("""CREATE TABLE IF NOT EXISTS webhooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        secret TEXT DEFAULT '',
        events TEXT DEFAULT '*',        -- JSON 数组，["*"] 表示全订阅
        enabled INTEGER DEFAULT 1,
        created_at REAL DEFAULT (strftime('%s','now')),
        last_triggered REAL DEFAULT 0,
        fail_count INTEGER DEFAULT 0
    )""")
    c.commit()


def register_webhook(url, events=None, secret="", enabled=True):
    """注册一个 webhook。返回 webhook id。"""
    init_events()
    c = _conn()
    events_json = json.dumps(events or ["*"], ensure_ascii=False)
    c.execute("INSERT INTO webhooks (url, secret, events, enabled) VALUES (?, ?, ?, ?)",
              (url, secret or "", events_json, 1 if enabled else 0))
    c.commit()
    wid = c.lastrowid
    c.close()
    return wid


def list_webhooks():
    init_events()
    c = _conn()
    rows = c.execute(
        "SELECT id, url, secret, events, enabled, created_at, last_triggered, fail_count "
        "FROM webhooks ORDER BY id").fetchall()
    c.close()
    result = []
    for r in rows:
        evts = json.loads(r[3]) if r[3] else ["*"]
        result.append({
            "id": r[0], "url": r[1], "has_secret": bool(r[2]),
            "events": evts, "enabled": bool(r[4]),
            "created_at": r[5], "last_triggered": r[6] or 0,
            "fail_count": r[7] or 0,
        })
    return result


def update_webhook(wid, **kw):
    init_events()
    allowed = {"url", "secret", "events", "enabled"}
    sets = []
    vals = []
    for k, v in kw.items():
        if k not in allowed:
            continue
        if k == "events":
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return False
    vals.append(wid)
    c = _conn()
    c.execute(f"UPDATE webhooks SET {','.join(sets)} WHERE id=?", vals)
    c.commit()
    ok = c.total_changes > 0
    c.close()
    return ok


def delete_webhook(wid):
    init_events()
    c = _conn()
    c.execute("DELETE FROM webhooks WHERE id=?", (wid,))
    c.commit()
    ok = c.total_changes > 0
    c.close()
    return ok


# ---------------- 事件发射 ----------------

def emit(event_type, data=None):
    """发射一个事件：写入通知缓冲 + 异步派发 webhook。"""
    evt = {
        "type": event_type,
        "data": data or {},
        "timestamp": time.time(),
    }

    # 写入环形缓冲
    with _notifications_lock:
        _notifications.append(evt)

    # 异步派发
    with _dispatch_cv:
        _dispatch_q.append(evt)
        _dispatch_cv.notify()

    return evt


def get_notifications(since=None, limit=50):
    """获取最近的站内通知。"""
    with _notifications_lock:
        items = list(_notifications)
    if since is not None:
        items = [i for i in items if i["timestamp"] > since]
    return items[-limit:]


# ---------------- Webhook 异步派发 ----------------

def _sign_payload(payload, secret):
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _dispatch_async(evt):
    """把事件 POST 到所有匹配的 webhook。"""
    init_events()
    c = _conn()
    rows = c.execute(
        "SELECT id, url, secret, events, fail_count FROM webhooks WHERE enabled=1").fetchall()
    c.close()

    payload = json.dumps(evt, ensure_ascii=False, default=str)
    for wid, url, secret, evts_json, fail_count in rows:
        evts = json.loads(evts_json) if evts_json else ["*"]
        if "*" not in evts and evt["type"] not in evts:
            continue
        try:
            headers = {"Content-Type": "application/json", "X-Harbor-Event": evt["type"]}
            sig = _sign_payload(payload, secret)
            if sig:
                headers["X-Harbor-Signature"] = f"sha256={sig}"
            req = urllib.request.Request(
                url, data=payload.encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                _ = resp.read()
            # 成功 → 重置失败计数
            c2 = _conn()
            c2.execute("UPDATE webhooks SET last_triggered=?, fail_count=0 WHERE id=?",
                       (time.time(), wid))
            c2.commit()
            c2.close()
        except Exception as e:
            new_fail = (fail_count or 0) + 1
            c2 = _conn()
            # 连续失败 5 次就自动禁用，避免一直刷
            c2.execute("UPDATE webhooks SET fail_count=?, enabled=? WHERE id=?",
                       (new_fail, 1 if new_fail < 5 else 0, wid))
            c2.commit()
            c2.close()


def _dispatcher_loop():
    global _dispatcher_running
    _dispatcher_running = True
    while _dispatcher_running:
        with _dispatch_cv:
            while not _dispatch_q and _dispatcher_running:
                _dispatch_cv.wait(timeout=1.0)
            if not _dispatcher_running:
                break
            evt = None
            if _dispatch_q:
                evt = _dispatch_q.popleft()
        if evt:
            _dispatch_async(evt)


_dispatcher_thread = None

def start_dispatcher():
    global _dispatcher_thread
    if _dispatcher_thread is None:
        _dispatcher_thread = threading.Thread(target=_dispatcher_loop, daemon=True,
                                              name="event-dispatcher")
        _dispatcher_thread.start()


def stop_dispatcher():
    global _dispatcher_running
    _dispatcher_running = False
    with _dispatch_cv:
        _dispatch_cv.notify()


# ---------------- 快捷：从 Hub / TaskManager 触发的事件包装 ----------------

def on_task_complete(task):
    """任务完成/失败/等人工时，根据类型触发对应事件。"""
    kind = task.get("kind", "")
    status = task.get("status", "")
    article_id = task.get("article_id")

    if status == "ok":
        emit("task.ok", {"task_id": task.get("task_id"), "kind": kind, "article_id": article_id})
        if kind == "publish":
            result = task.get("result", {})
            platforms = []
            if isinstance(result, list):
                platforms = [r.get("platform") for r in result if isinstance(r, dict)]
            elif isinstance(result, dict) and "results" in result:
                platforms = [r.get("platform") for r in result["results"] if isinstance(r, dict)]
            emit("publish.ok", {"task_id": task.get("task_id"), "article_id": article_id,
                                "platforms": platforms})
    elif status == "failed":
        emit("task.failed", {"task_id": task.get("task_id"), "kind": kind,
                             "error": task.get("error", "")[:200]})
        if kind == "publish":
            emit("publish.failed", {"task_id": task.get("task_id"), "article_id": article_id,
                                    "error": task.get("error", "")[:200]})
    elif status == "waiting_human":
        emit("task.waiting_human", {"task_id": task.get("task_id"), "kind": kind,
                                    "message": task.get("message", "")})


# 启动派发线程
start_dispatcher()
