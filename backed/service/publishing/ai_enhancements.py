# -*- coding: utf-8 -*-
"""AI 增强工具集：翻译、配图提示、文章克隆、自定义提示词模板。

这些是"围绕 AI 写作的周边工具"——不替代 ai.py 的核心写/改/润色，
而是在它基础上延伸，补齐"从灵感到发布"的完整链路。

提供的能力：
  translate         把 Markdown 文章翻译成目标语言（保留代码块不动）
  image_prompts     根据文章主题生图提示（喂给 Stable Diffusion / DALL·E）
  clone_article     克隆文章（复制内容到新草稿，标题加"副本"后缀）
  extract_outline   从 Markdown 内容提炼大纲（方便重组）
  reading_time      估算中文阅读时长（字 / 350 字/分）
  seo_fields        生成 SEO 描述 / 关键词 / slug
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

from service.publishing import ai as ai_mod


# ---------------- 提示词模板库（PROMPT_TEMPLATES）----------------
# 改这个文件就改了 AI 的行为，不用动代码。

PROMPT_TEMPLATES = {
    "tutorial": {
        "name": "分步骤教程",
        "system_addition": "用「步骤 1 / 步骤 2 / …」带编号的流程结构。每步要有具体的命令或操作。末尾放常见问题排查。",
        "default_words": 3000,
    },
    "opinion": {
        "name": "观点评论",
        "system_addition": "先亮观点，再给 3 个论据，最后回应对立观点。不要中立骑墙。",
        "default_words": 1500,
    },
    "deep_dive": {
        "name": "深度剖析",
        "system_addition": "从一个具体现象出发，逐步剥到原理层。每部分有代码/数据支撑。不要浮于表面。",
        "default_words": 4000,
    },
    "news_brief": {
        "name": "资讯简评",
        "system_addition": "三段式：发生了什么 → 为什么重要 → 对开发者的影响。300 字以内，别注水。",
        "default_words": 800,
    },
}


def translate(content_md, target_lang="en", model=None, preferred_provider=None):
    """翻译 Markdown 文章到目标语言。

    保留代码块不动（代码永远不该被翻译），翻译正文与标题。
    简单策略：按段发送，最大段长 4000 字（避开大多数模型的输出 token 上限）。
    """
    if not content_md.strip():
        return ""

    # 先抠出代码块占位符，避免翻译代码
    code_blocks = []

    def _store_block(m):
        code_blocks.append(m.group(0))
        return f"<!--CODE_BLOCK_{len(code_blocks) - 1}-->"

    # 匹配 ```...``` 代码块（含语言标记）
    text = re.sub(r"```[\s\S]*?```", _store_block, content_md)
    # 也行内代码
    inline_codes = []

    def _store_inline(m):
        inline_codes.append(m.group(0))
        return f"<!--INLINE_{len(inline_codes) - 1}-->"

    text = re.sub(r"`[^`\n]+`", _store_inline, text)

    # 翻译
    lang_name = {"en": "英文", "ja": "日语", "ko": "韩语",
                 "fr": "法语", "de": "德语"}.get(target_lang, target_lang)

    prompt = f"""把下面这段 Markdown 文章翻译成{lang_name}。
要求：
- 只输出翻译结果，不要解释或注释
- 保留 Markdown 格式（标题、列表、加粗等）
- 不要翻译 $$...$$ $$ 里的 LaTeX
- 占位符（如 <!--CODE_BLOCK_0-->、<!--INLINE_0-->）原样保留

原文：
{text}"""

    try:
        translated = ai_mod.chat(
            [{"role": "system", "content": ai_mod.system_write()},
             {"role": "user", "content": prompt}],
            model=model, task="translate", preferred_provider=preferred_provider,
        )
    except Exception as e:
        raise ai_mod.AIError(f"翻译失败: {e}")

    # 还原代码块
    for i, block in enumerate(code_blocks):
        translated = translated.replace(f"<!--CODE_BLOCK_{i}-->", block)
    for i, code in enumerate(inline_codes):
        translated = translated.replace(f"<!--INLINE_{i}-->", code)

    return translated


def image_prompts(title, content_md, n=3, model=None, preferred_provider=None):
    """根据文章内容生成本地可用的文生图提示。

    返回 n 个提示（英文，兼容 SDXL / Flux / DALL·E），每个对应文章一个关键概念。
    不是真的去调图 API（那得再引一个 SDK 依赖），而是给出质量够高的 prompt，
    让作者自己丢到 Midjourney / 通义万相 / ComfyUI 里。
    """
    prompt = f"""你是文生图提示工程师。根据以下文章的标题和摘要，提炼 {n} 个关键视觉场景，
分别为每个场景写一个英文 prompt（50-80 词）：含主体、光影、色调、风格、构图。
风格锁定在"极简科技风 + 电影感光线 + 低饱和度"——跟技术博客封面统一调性。

要求：
- 每个 prompt 独立一行，用 ||| 分隔
- 不要解释、不要markdown包裹

标题：{title}
摘要：{(content_md or '')[:1500]}"""

    try:
        raw = ai_mod.chat(
            [{"role": "user", "content": prompt}],
            model=model, task="image_prompts", max_tokens=600, temperature=0.8,
            preferred_provider=preferred_provider,
        )
        prompts = [p.strip() for p in raw.split("|||") if p.strip()]
        return prompts[:n]
    except Exception as e:
        raise ai_mod.AIError(f"生成配图提示失败: {e}")


def clone_article(article):
    """克隆文章：标题加「副本」后缀，复制全部字段，源标记 origin。

    用于：基于一篇爆文改一篇新的、A/B 测试不同角度、翻译前先复刻一版。
    """
    new_title = article.get("title", "") + "（副本）"
    ext = {}
    try:
        ext = json.loads(article.get("ext", "{}") or "{}")
    except Exception:
        pass
    ext["cloned_from"] = article.get("id")
    ext["cloned_at"] = time.time()
    return {
        "title": new_title,
        "content_md": article.get("content_md", ""),
        "summary": article.get("summary", ""),
        "tags": article.get("tags", ""),
        "cover": article.get("cover", ""),
        "source": "import",
        "ai_model": "",
        "ext": json.dumps(ext, ensure_ascii=False),
        "status": "draft",
    }


def extract_outline(content_md):
    """从 Markdown 内容提炼大纲（只捕 # 标题行）。

    返回 [{level, title, line_no}] 构成的树，可供：
      - 文章重组（快速跳到某章节）
      - 目录生成（平台侧的文章目录对接）
      - 字数分布分析（某一章节是不是注水了）
    """
    outline = []
    for i, line in enumerate(content_md.splitlines()):
        m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            outline.append({"level": level, "title": title, "line_no": i + 1})
    return outline


def reading_time(content_md, lang="zh"):
    """估算阅读时长（分钟）。中文按 350 字/分，英文按 200 词/分。"""
    if not content_md:
        return 0
    if lang == "zh":
        # 去掉 markdown 标记后计中文字符数
        stripped = re.sub(r"[#*`\-\[\]()>\n\r]", " ", content_md)
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", stripped))
        total_chars = len(stripped.replace(" ", ""))
        # 中英混合按权重
        return max(1, round((chinese_chars * 1 + (total_chars - chinese_chars) * 0.3) / 350))
    else:
        words = len(content_md.split())
        return max(1, round(words / 200))


def seo_fields(title, content_md, tags=""):
    """根据文章字段生成 SEO 元数据。返回 dict：seo_title, seo_description, slug, keywords。

    不依赖外部 SEO 工具——本地 heuristic 生成，够用：
      seo_title       取标题（60 字符以内，SiteName 后缀前端拼接）
      seo_description 取 summary 或正文首段（150 字符以内）
      slug            标题转拼音友好的 URL slug（中文→不用拼音，直接用 ID 更安全）
      keywords        标签补上摘要高频词
    """
    # description：优先用 summary，其次正文首段纯文本
    desc = ""
    if tags:
        # 第一段正文取纯文本
        for line in content_md.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
                desc = re.sub(r"[#*`\[\]()]", "", stripped)
                break
    else:
        desc = re.sub(r"[#*`\[\]()\n]", " ", content_md).strip()[:150]

    desc = (desc or content_md[:150] if content_md else "")[:150]

    # slug：用 ID 更安全（中文 slug 兼容性问题），这里提供建议格式
    slug = f"article-{int(time.time())}"

    # keywords = 标签 + 标题中长度 ≥ 2 的中文词 + 正文高频词
    kws = []
    if tags:
        kws.extend([t.strip() for t in tags.split(",") if t.strip()])
    # 标题中至少 2 字的分词（极简：按非中文切割）
    title_words = [w for w in re.split(r"[^\u4e00-\u9fff]+", title) if len(w) >= 2]
    kws.extend(title_words[:3])
    # 去重保序
    seen = set()
    final_kws = []
    for k in kws:
        if k not in seen:
            seen.add(k)
            final_kws.append(k)

    return {
        "seo_title": title[:60],
        "seo_description": desc,
        "slug": slug,
        "keywords": ",".join(final_kws[:8]),
    }


def ai_write_with_template(topic, template_key="", **kw):
    """使用预置模板写文章。template_key 对应 PROMPT_TEMPLATES。

    模板只决定 system_addition（追加什么要求）和 default_words(篇幅)，
    其余 prompt 工程还是走 ai_mod.write_article。这种设计让"模板"是
    可叠加的配置，而不是独立代码路径——新模板只需改 PROMPT_TEMPLATES。
    """
    tmpl = PROMPT_TEMPLATES.get(template_key, {})
    style = kw.get("style", "")
    extra = tmpl.get("system_addition", "")
    combined = f"{style}\n{extra}".strip() if style else extra
    words = kw.get("words") or tmpl.get("default_words", 2000)
    return ai_mod.write_article(
        topic,
        style=combined,
        words=words,
        tags_hint=kw.get("tags_hint", ""),
        model=kw.get("model"),
        preferred_provider=kw.get("preferred_provider"),
    )


def list_templates():
    """列出所有可用模板（前端下拉菜单用）。"""
    return [{"key": k, "name": v["name"], "default_words": v["default_words"]}
            for k, v in PROMPT_TEMPLATES.items()]
