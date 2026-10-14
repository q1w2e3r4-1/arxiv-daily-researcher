"""Render saved reading reports as a self-contained PDF, without network IO."""
from __future__ import annotations

import html
import io
import re
from typing import Any

LABELS = {
    "summary": "背景与问题", "innovations": "关键观察与挑战",
    "methodology": "核心思路与设计", "key_results": "结果与总结",
    "tech_stack": "技术栈", "strengths": "优点", "weaknesses": "不足",
    "custom_answers": "自定义问题",
}


def inline(value: Any) -> str:
    text = html.escape(str(value))
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    return re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)


def markdown(value: Any) -> str:
    if isinstance(value, list):
        return "<ul>" + "".join(f"<li>{markdown(v)}</li>" for v in value) + "</ul>"
    if isinstance(value, dict):
        return "".join(f"<p><b>{html.escape(str(k))}</b></p>{markdown(v)}" for k, v in value.items())
    output, paragraph = [], []
    kind = ""

    def flush():
        if paragraph:
            output.append("<p>" + "<br>".join(paragraph) + "</p>")
            paragraph.clear()

    def close():
        nonlocal kind
        if kind:
            output.append(f"</{kind}>")
            kind = ""

    for line in str(value).splitlines():
        if not line.strip():
            flush()
            continue
        match = re.match(r"^\s*(?:(\d+)[.)、]\s+|[-*•]\s+)(.*)$", line)
        if match:
            flush()
            wanted = "ol" if match[1] else "ul"
            if wanted != kind:
                close()
                kind = wanted
                output.append(f"<{kind}>")
            output.append(f"<li>{inline(match[2])}</li>")
        else:
            close()
            paragraph.append(inline(re.sub(r"^#{1,6}\s+", "", line)))
    flush()
    close()
    return "".join(output)


def paper_tldr(item: dict) -> str:
    variants = item.get("variants") or []
    preferred = [v for v in variants if (v.get("source"), v.get("paper_id")) == (item.get("source"), item.get("paper_id"))]
    ordered = preferred + [v for v in variants if v not in preferred]
    for variant in ordered:
        analysis = variant.get("analysis") or {}
        if not isinstance(analysis, dict):
            continue
        tldr = analysis.get("full_text_tldr")
        meta = analysis.get("__meta") or {}
        if isinstance(meta, dict) and meta.get("content_source") == "pdf" and isinstance(tldr, str) and tldr.strip():
            return tldr
    return item.get("tldr") or next((v["tldr"] for v in ordered if v.get("tldr")), "")


def reports_html(items: list[dict]) -> str:
    parts = [f"<h1>论文阅读报告</h1><p>共 {len(items)} 篇，按勾选顺序排列。使用已保存的分析，不重新生成。</p>"]
    for index, item in enumerate(items, 1):
        parts.append(f'<div class="paper"><h2>{index}. {html.escape(str(item.get("title") or "未命名论文"))}</h2>')
        if item.get("authors"):
            parts.append(f'<p>作者：{html.escape(", ".join(item["authors"]))}</p>')
        tldr = paper_tldr(item)
        if tldr:
            parts.append(f"<p><b>TL;DR：</b>{inline(tldr)}</p>")
        variants = item.get("variants") or []
        if not variants:
            parts.append("<p>尚无已保存的阅读报告。</p>")
        for variant in variants:
            parts.append(f'<h3>来源：{html.escape(str(variant.get("source") or "未知"))}</h3>')
            # Print URLs as escaped text, never fetch or interpret them as HTML.
            if variant.get("url"):
                parts.append(f'<p class="muted">{html.escape(str(variant["url"]))}</p>')
            analysis = variant.get("analysis")
            if not isinstance(analysis, dict):
                parts.append("<p>尚无已保存的阅读报告。</p>")
                continue
            meta = analysis.get("__meta") or {}
            source = meta.get("content_source") if isinstance(meta, dict) else None
            provenance = {"pdf": "基于 PDF 正文", "abstract_fallback": "基于摘要，未获得 PDF 正文"}.get(source, "历史分析，正文来源未记录")
            parts.append(f'<p class="muted">{provenance}</p>')
            if analysis.get("chinese_title"):
                parts.append(f'<h3>{html.escape(str(analysis["chinese_title"]))}</h3>')
            keys = list(LABELS) + [k for k in analysis if k not in LABELS]
            sections = 0
            for key in keys:
                if key.startswith("__") or key in {"chinese_title", "full_text_tldr", "editorial_review"}:
                    continue
                value = analysis.get(key)
                if value is None or value == [] or value == {} or (isinstance(value, str) and not value.strip()):
                    continue
                parts.append(f'<h4>{html.escape(LABELS.get(key, key))}</h4>{markdown(value)}')
                sections += 1
            if not sections:
                parts.append("<p>尚无已保存的阅读报告正文。</p>")
        parts.append("</div>")
    body = "".join(parts)
    if len(body.encode("utf-8")) > 4_000_000:
        raise ValueError("报告内容过大，请减少本次导出的论文数。")
    return body


def render_pdf(items: list[dict]) -> bytes:
    import fitz

    body = reports_html(items)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    story = fitz.Story(html=body, user_css="""
        body { font-family: sans-serif; font-size: 11pt; line-height: 1.5; }
        h1 { font-size: 22pt; } h2 { font-size: 17pt; }
        h3 { font-size: 13pt; } h4 { font-size: 12pt; }
        .muted { color: #555; font-size: 9pt; }
        li { margin-bottom: 6pt; } p { margin-bottom: 8pt; }
    """)
    def page_rect(index, _filled):
        if index >= 1000:
            raise ValueError("报告页数过多，请减少本次导出的论文数。")
        return fitz.Rect(0, 0, 595, 842), fitz.Rect(42, 42, 553, 800), None

    try:
        story.write(writer, page_rect)
    finally:
        writer.close()
    return buffer.getvalue()
