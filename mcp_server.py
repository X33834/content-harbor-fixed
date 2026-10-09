#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Content Harbor MCP Server — 让任意 AI Agent 通过 MCP 协议操控内容港。

启动（stdio 模式）：
    python mcp_server.py

启动（SSE/HTTP 模式，多客户端）：
    python mcp_server.py --transport sse --port 8900

注册到 Claude Code / Cursor / Windsurf：
    claude mcp add --transport stdio content-harbor python /path/to/mcp_server.py
    # 或 .mcp.json:
    {
      "mcpServers": {
        "content-harbor": {
          "command": "python",
          "args": ["/path/to/content-harbor/mcp_server.py"]
        }
      }
    }
"""

import sys
import os
from pathlib import Path

# 把 backed/ 加入 Python 路径，确保能 import service
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR / "backed"))

from fastmcp import FastMCP

from service.publishing.service import Hub

# ── 单例 Hub（MCP server 进程内只启一次）──────────────────────────
_hub = None


def _get_hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub(headless=True)
    return _hub


mcp = FastMCP("content-harbor")


# ── 文章 ────────────────────────────────────────────────────────────

@mcp.tool()
def list_articles(status: str = None, limit: int = 20) -> list:
    """列出文章列表。status 可选：draft/published/review/archived。"""
    return _get_hub().list(status=status, limit=limit)


@mcp.tool()
def get_article(article_id: int) -> dict:
    """按 ID 获取文章完整字段（标题/正文/摘要/标签/状态）。"""
    r = _get_hub().get(article_id)
    if not r:
        raise ValueError(f"文章 {article_id} 不存在")
    return dict(r)


@mcp.tool()
def create_article(title: str, content_md: str = "", summary: str = "",
                    tags: str = "") -> dict:
    """新建一篇文章，返回 {id, title}。"""
    aid = _get_hub().create(title, content_md, summary=summary, tags=tags,
                             source="human")
    return {"id": aid, "title": title}


@mcp.tool()
def update_article(article_id: int, title: str = None, content_md: str = None,
                    summary: str = None, tags: str = None, status: str = None) -> dict:
    """更新文章的任意字段。内容变更后会自动 pend 已发布平台的同步。"""
    kw = {k: v for k, v in locals().items()
          if k != "article_id" and v is not None}
    kw.pop("article_id")
    ok, pending = _get_hub().edit(article_id, **kw)
    return {"ok": ok, "pending_sync": pending}


# ── AI 写稿 ──────────────────────────────────────────────────────────

@mcp.tool()
def ai_write_article(topic: str, words: int = 2000, tags_hint: str = "",
                      model: str = "", publish_to: list = None,
                      style: str = "") -> dict:
    """让 AI 写一篇技术文章，自动入库。可选直接发布到指定平台。

    model: "provider:model" 指定模型（如 "openai:gpt-4o"），不指定走 premium 路由。
    publish_to: ["juejin","csdn"] 写完直接发（草稿模式，需人工确认上线）。
    """
    return _get_hub().ai_write(topic, style=style, words=words,
                                tags_hint=tags_hint, publish_to=publish_to,
                                model=model or None)


@mcp.tool()
def ai_rewrite_article(article_id: int, instruction: str,
                        model: str = "") -> dict:
    """按指令 AI 改写已有文章（如"更口语""补充踩坑章节""压缩到 800 字"）。"""
    return _get_hub().ai_rewrite(article_id, instruction,
                                  model=model or None)


@mcp.tool()
def ai_polish_article(article_id: int, model: str = "") -> dict:
    """AI 润色文章：修错别字、顺语句、统一代码块语言标识。"""
    return _get_hub().ai_polish(article_id, model=model or None)


@mcp.tool()
def ai_translate_article(article_id: int, target_lang: str = "en",
                          model: str = "") -> dict:
    """翻译文章到目标语言（en/ja/ko/fr/de），保留代码块不动。"""
    return _get_hub().ai_translate(article_id, target_lang, model=model or None)


@mcp.tool()
def ai_image_prompts(article_id: int, n: int = 3) -> dict:
    """根据文章内容生成 n 个英文文生图 prompt（兼容 SDXL/Flux/DALL·E）。"""
    return _get_hub().ai_image_prompts(article_id, n)


# ── 发布 ────────────────────────────────────────────────────────────

@mcp.tool()
def publish_article(article_id: int, platforms: list,
                     draft_only: bool = False, account: str = "default") -> dict:
    """异步发布文章到指定平台，返回 task_id。用 get_task 查询进度。"""
    from service.publishing.tasks import TaskManager
    conn = _get_hub().conn
    task_id = _get_hub().tasks.submit("publish", article_id=article_id,
                                       platforms=platforms, account=account,
                                       draft_only=draft_only)
    return {"task_id": task_id, "status": "pending",
            "poll": f"GET /tasks/{task_id}"}


@mcp.tool()
def update_remote_article(article_id: int, platforms: list = None,
                           account: str = "default") -> dict:
    """原地更新（不是重发）：打开已发布平台的编辑页改内容并保存。"""
    task_id = _get_hub().tasks.submit("update", article_id=article_id,
                                       platforms=platforms, account=account)
    return {"task_id": task_id, "status": "pending"}


@mcp.tool()
def list_platforms() -> list:
    """列出所有可用平台及其在线状态。"""
    from service.publishing.adapters.base import ADAPTERS
    return [{"id": a.id, "name": a.name, "needs_browser": a.needs_browser}
            for a in ADAPTERS.values()]


@mcp.tool()
def list_providers() -> list:
    """列出所有已配置的 AI Provider + 可用模型 + 价格级别。"""
    return _get_hub().list_models()


# ── 任务管理 ──────────────────────────────────────────────────────────

@mcp.tool()
def get_task(task_id: str) -> dict:
    """查询任务状态（pending/running/ok/failed/waiting_human）。"""
    t = _get_hub().tasks.get(task_id)
    if not t:
        raise ValueError(f"任务 {task_id} 不存在")
    return dict(t)


@mcp.tool()
def resume_task(task_id: str, approved: bool = True) -> dict:
    """恢复等待人工的任务。approved=True 重跑；False 标记放弃。"""
    return _get_hub().tasks.resume(task_id, approved=approved)


# ── 内容质检 ──────────────────────────────────────────────────────────

@mcp.tool()
def quality_check(article_id: int) -> dict:
    """对文章运行内容质检：可读性评分 + SEO 评分 + 库内重复度 + 改进建议。"""
    return _get_hub().content_qa(article_id=article_id)


@mcp.tool()
def analyze_text(content_md: str, title: str = "", summary: str = "",
                  tags: str = "") -> dict:
    """对任意文本（不保存入库）运行内容质检。"""
    return _get_hub().content_qa(content_md=content_md, title=title,
                                  summary=summary, tags=tags)


# ── 标签 ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_tags(limit: int = 30) -> list:
    """列出热门标签及其出现次数。"""
    from service.publishing.tags import list_tags
    return list_tags(_get_hub().conn, limit=limit)


@mcp.tool()
def suggest_tags(title: str, content_md: str) -> list:
    """根据标题 + 正文推荐 3-5 个标签。"""
    from service.publishing.tags import suggest_for_article
    return suggest_for_article(_get_hub().conn, title, content_md)


# ── 内容导入 ──────────────────────────────────────────────────────────

@mcp.tool()
def import_markdown(path: str, tags: str = "") -> dict:
    """导入本地 Markdown 文件，自动提取 front-matter 元数据。"""
    aid = _get_hub().import_md(path, tags=tags)
    return {"id": aid}


# ── 入口 ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Content Harbor MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8900)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
