# -*- coding: utf-8 -*-
"""内容质检：零外部依赖的本地评分引擎。

三大维度：
  1. 可读性(rich du) — 句子长短、段落结构、词汇密度、标题层级
  2. SEO  — 关键词密度、标题/TDK 完整度、内链图片 Alt
  3. 重复度 — 与库内其他文章的 MinHash-LSH 近似查重

全部纯 heuristic，不调 AI，不联网。score 范围 0-100。
"""

import math
import re
import hashlib
from collections import Counter


# ---------------- 可读性 ----------------

def _strip_md(text):
    """去掉 Markdown 记号，返回纯文本。"""
    text = re.sub(r"```[\s\S]*?```", "", text)     # 整段代码去掉
    text = re.sub(r"`[^`\n]+`", "", text)           # 行内代码
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接/图片
    text = re.sub(r"[#*_~>|`\-\n\r]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def readability_score(content_md):
    """可读性评分 0-100。考虑：平均句长、段落长度、标题占比、代码占比。"""
    if not content_md or len(content_md.strip()) < 30:
        return {"score": 0, "label": "太短", "detail": "正文不足 30 字"}

    text = _strip_md(content_md)

    # 句子拆分（中英文标点）
    sentences = re.split(r'[。！？!?.]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = text.replace(" ", "")

    char_count = len(words)
    sent_count = max(1, len(sentences))
    avg_sent_len = char_count / sent_count

    # 段落数
    paragraphs = [p for p in content_md.split("\n\n") if p.strip()]
    para_count = max(1, len(paragraphs))
    avg_para_len = char_count / para_count

    # 标题占比
    headings = re.findall(r"^#{1,6}\s+", content_md, re.M)
    heading_ratio = len(headings) / para_count if para_count else 0

    # 代码占比（超过 40% 可读性下降）
    code_chars = len(re.findall(r"```[\s\S]*?```", content_md))
    code_ratio = code_chars / max(1, char_count)

    # --- 评分规则 ---
    score = 70  # 基础分

    # 平均句长：15-25 字最优，超出扣分
    if avg_sent_len < 8:
        score -= 5  # 太碎
    elif 8 <= avg_sent_len <= 30:
        score += 10
    elif 30 < avg_sent_len <= 60:
        score -= int((avg_sent_len - 30) * 0.5)
    else:
        score -= 20  # 句子太长

    # 段落长度：100-300 字/段最优
    if 80 <= avg_para_len <= 350:
        score += 8
    elif avg_para_len > 600:
        score -= 10  # 段落太长

    # 标题过多或过少
    if heading_ratio >= 0.1:
        score += 7
    elif heading_ratio < 0.03 and char_count > 500:
        score -= 8  # 长篇无标题

    # 代码占比
    if code_ratio > 0.5:
        score -= int((code_ratio - 0.5) * 30)

    # 加分：有列表、有段落
    if re.search(r"^[-*+]\s", content_md, re.M):
        score += 3
    if re.search(r"^\d+[.)]\s", content_md, re.M):
        score += 2

    score = max(0, min(100, score))

    label = "优" if score >= 80 else "良" if score >= 60 else "中" if score >= 40 else "差"
    return {"score": score, "label": label,
            "detail": f"平均句 {avg_sent_len:.0f} 字、{para_count} 段、代码 {code_ratio:.0%}"}


# ---------------- SEO 评分 ----------------

def seo_score(title, content_md, summary="", tags=""):
    """SEO 评分 0-100。考察：标题长度、TDK 完整度、关键词密度、H 标签结构。"""
    score = 50
    tips = []

    # 标题：25-35 中文字最优
    tlen = len(_strip_md(title))
    if 15 <= tlen <= 45:
        score += 10
    elif tlen < 10:
        score -= 10
        tips.append("标题过短（< 10 字）")
    elif tlen > 60:
        score -= 5
        tips.append("标题过长（> 60 字）")

    # description
    desc = _strip_md(summary) if summary else ""
    dlen = len(desc)
    if 50 <= dlen <= 160:
        score += 10
    elif dlen > 0 and dlen < 30:
        score -= 5
        tips.append("摘要过短（< 30 字）")
    elif dlen == 0:
        tips.append("缺少摘要（各平台 SEO 受影响）")

    # 标签（keywords）
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if 2 <= len(tag_list) <= 5:
        score += 8
    elif len(tag_list) == 0:
        score -= 5
        tips.append("缺少标签")

    # 正文关键词密度：标题词在正文中的分布
    text = _strip_md(content_md)
    title_words = set(re.split(r"[^\u4e00-\u9fff]+", _strip_md(title)))
    title_words = {w for w in title_words if len(w) >= 2}
    if title_words and text:
        hit = sum(1 for w in title_words if w in text)
        ratio = hit / len(title_words)
        if ratio >= 0.5:
            score += 8
        elif ratio < 0.2 and text:
            tips.append("标题关键词在正文中出现不足")

    # H 标签结构：必须有 H2，H 标签不应跳跃
    h_levels = [len(m) for m in re.findall(r"^(#{1,6})\s", content_md, re.M)]
    if 2 in h_levels:
        score += 10
    elif h_levels and h_levels[0] == 1:
        # 有 H1 但没 H2
        score -= 3
        tips.append("只有 H1 无 H2，建议拆分章节")

    # 正文长度
    char_count = len(text)
    if char_count >= 1500:
        score += 5
    elif char_count < 300:
        score -= 10
        tips.append("正文过短（< 300 字），搜索引擎不倾向收录")

    # 图片 alt
    imgs = re.findall(r"!\[([^\]]*)\]\([^)]*\)", content_md)
    if imgs:
        with_alt = sum(1 for a in imgs if a.strip())
        if with_alt == len(imgs):
            score += 5
        else:
            tips.append(f"{len(imgs) - with_alt} 张图片缺少 alt")

    # 内链
    links = re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", content_md)
    if len(links) >= 2:
        score += 5

    score = max(0, min(100, score))
    label = "优秀" if score >= 85 else "良好" if score >= 70 else "一般" if score >= 50 else "需优化"
    return {"score": score, "label": label, "tips": tips[:5]}


# ---------------- 重复度检测 ----------------

def _shingles(text, k=3):
    """把文本拆成 k-shingle（字符级别，适配中文）。"""
    text = re.sub(r"\s+", "", text.lower())
    if len(text) < k:
        return {text} if text else set()
    return {text[i:i + k] for i in range(len(text) - k + 1)}


def _minhash(shingles, num_hashes=32):
    """极简 MinHash：多 hash 取最小值。"""
    signatures = []
    for seed in range(num_hashes):
        min_val = float('inf')
        for s in shingles:
            # 稳定 hash
            h = int(hashlib.md5(f"{seed}:{s}".encode()).hexdigest(), 16)
            if h < min_val:
                min_val = h
        signatures.append(min_val)
    return signatures


def _jaccard(sign_a, sign_b):
    """近似 Jaccard = 相同签名数 / 总签名数。"""
    if not sign_a or not sign_b:
        return 0.0
    common = sum(1 for a, b in zip(sign_a, sign_b) if a == b)
    return common / max(len(sign_a), len(sign_b))


def check_similarity(target_md, other_articles, threshold=0.3):
    """计算目标文章与已有文章的相似度。返回相似度 > threshold 的列表。"""
    target_text = _strip_md(target_md)[:5000]
    target_shingles = _shingles(target_text)
    target_sig = _minhash(target_shingles)

    similar = []
    for art in other_articles:
        aid = art.get("id")
        other_text = _strip_md(art.get("content_md", ""))[:5000]
        if not other_text:
            continue
        other_shingles = _shingles(other_text)
        # 先求精确 jaccard 做快速排除
        intersection = len(target_shingles & other_shingles)
        union = len(target_shingles | other_shingles)
        if union == 0 or intersection / union < threshold * 0.5:
            continue
        other_sig = _minhash(other_shingles)
        sim = _jaccard(target_sig, other_sig)
        if sim >= threshold:
            similar.append({
                "id": aid,
                "title": art.get("title", "未命名"),
                "similarity": round(sim, 3),
            })

    similar.sort(key=lambda x: -x["similarity"])
    return similar


# ---------------- 总分 ----------------

def full_qa(article, other_articles=None):
    """运行全部质检。返回总分 + 分项 + 改进建议。"""
    title = article.get("title", "")
    content_md = article.get("content_md", "")
    summary = article.get("summary", "")
    tags = article.get("tags", "")

    rd = readability_score(content_md)
    so = seo_score(title, content_md, summary, tags)
    sim = check_similarity(content_md, other_articles or [], threshold=0.35)

    # 总分加权：可读性 40% + SEO 40% + 重复度惩罚 20%
    dedup_penalty = min(20, len(sim) * 10)
    total = max(0, int(rd["score"] * 0.4 + so["score"] * 0.4 + (100 - dedup_penalty) * 0.2))

    tips = list(so.get("tips", []))
    if rd["score"] < 60:
        tips.append(f"可读性仅 {rd['score']} 分：{_read_tip(content_md, rd)}")
    if sim:
        tips.append(f"与 {len(sim)} 篇库内文章相似度 > 35%（最相似：{sim[0]['title']}）")

    return {
        "total": total,
        "label": "优秀" if total >= 85 else "良好" if total >= 70 else "一般" if total >= 50 else "需优化",
        "readability": rd,
        "seo": so,
        "duplicates": sim,
        "tips": tips[:6],
    }


def _read_tip(content_md, rd):
    text = _strip_md(content_md)
    sentences = re.split(r'[。！？!?.]+', text)
    sentences = [s for s in sentences if s.strip()]
    avg = len(text) / max(1, len(sentences))
    if avg > 40:
        return "句子偏长，建议增加句号断句"
    paragraphs = [p for p in content_md.split("\n\n") if p.strip()]
    avg_para = len(text) / max(1, len(paragraphs))
    if avg_para > 500:
        return "段落偏长，建议拆分为小段落"
    return "建议适当增加标题结构、拆分长段落"
