"""Selected-paper export uses stored reports and never reads live user data."""
import json
from unittest.mock import patch

import fitz
import pytest
from starlette.testclient import TestClient

from modern_webui import app as webapp, backend
from modern_webui.paper_export import reports_html, render_pdf, paper_tldr
from utils.daily_research_store import DailyResearchStore
from test_paper_search import _seed_paper


def paper(title="通用推理加速"):
    return {"title": title, "source": "acm", "paper_id": "demo", "tldr": "Old scoring summary",
            "variants": [{"source": "acm", "paper_id": "demo", "url": "https://example.test/demo",
                          "analysis": {"__meta": {"content_source": "pdf", "secret": "hidden-marker"},
                                       "chinese_title": "中文标题", "full_text_tldr": "唯一全文总结",
                                       "summary": "背景说明", "innovations": "1. **缓存重复。** 需要共享。\n2. **调度瓶颈。** 减少等待。",
                                       "methodology": "核心设计", "key_results": "吞吐量提升",
                                       "legacy_field": ["保留旧字段"]}}]}


def text_of(content):
    with fitz.open(stream=content, filetype="pdf") as doc:
        return "".join(page.get_text() for page in doc), len(doc)


def test_pdf_is_chinese_expanded_ordered_and_preserves_sources():
    first = paper("第一篇论文")
    first["variants"].append({"source": "arxiv", "analysis": {"summary": "另一来源独立分析"}})
    second = paper("第二篇论文")
    second["variants"][0]["analysis"]["summary"] = "较长正文解释。" * 700
    content = render_pdf([first, second])
    assert content.startswith(b"%PDF")
    text, pages = text_of(content)
    assert pages > 3
    assert text.replace("\n", "").count("较长正文解释。") == 700
    assert text.index("第一篇论文") < text.index("第二篇论文")
    assert text.count("TL;DR") == 2
    assert text.count("唯一全文总结") == 2
    for value in ["背景与问题", "关键观察与挑战", "核心思路与设计", "结果与总结", "保留旧字段", "另一来源独立分析"]:
        assert value in text
    assert "hidden-marker" not in text and "Old scoring summary" not in text


def test_escaping_fallback_missing_and_size_budget():
    item = paper('<img src="https://example.test/x" onerror="alert(1)">')
    analysis = item["variants"][0]["analysis"]
    analysis["__meta"]["content_source"] = "abstract_fallback"
    analysis["summary"] = '<script>alert(1)</script> **重点**'
    assert paper_tldr(item) == "Old scoring summary"
    html = reports_html([item, {"title": "没有报告"}])
    assert "<img" not in html and "<script>" not in html
    assert "<b>重点</b>" in html
    assert "唯一全文总结" not in html
    text, _ = text_of(render_pdf([item, {"title": "没有报告"}]))
    assert "基于摘要" in text and "尚无已保存的阅读报告" in text
    analysis["summary"] = "a" * 4_000_001
    with pytest.raises(ValueError, match="内容过大"):
        reports_html([item])


def test_authenticated_export_reads_selection_without_mutation(tmp_path):
    store = DailyResearchStore(tmp_path / "isolated.db")
    for key in ["one", "two", "not-selected"]:
        _seed_paper(store, paper_id=key, title=key, authors=[], completed_at="2026-08-01T08:00:00")
        with store._connect() as conn:
            conn.execute("UPDATE daily_papers SET analysis_json=? WHERE paper_id=?", (json.dumps(paper()["variants"][0]["analysis"]), key))
    ids = {item["paper_id"]: item["entity_id"] for item in store.search_papers(limit=10)["items"]}
    with store._connect() as conn:
        before = list(conn.iterdump())
    with patch.object(webapp, "read_env", return_value={"WEBUI_AUTH_ENABLED": "false"}), patch.object(backend, "open_store", return_value=store), TestClient(webapp.app) as client:
        result = client.post("/api/papers/export", json={"entity_ids": [ids["two"], ids["one"]]})
        assert result.status_code == 200
        assert result.headers["content-type"] == "application/pdf"
        assert result.headers["cache-control"] == "no-store"
        assert "attachment" in result.headers["content-disposition"]
        text, _ = text_of(result.content)
        assert text.index("two") < text.index("one")
        assert "not-selected" not in text
        for invalid in [[], None, "one", [ids["one"]]*101, [ids["one"]]*2, ["unknown"], [123]]:
            assert client.post("/api/papers/export", json={"entity_ids": invalid}).status_code == 400
        with backend._PAPER_EXPORT_LOCK:
            assert client.post("/api/papers/export", json={"entity_ids": [ids["one"]]}).status_code == 400
    with store._connect() as conn:
        assert before == list(conn.iterdump())
    with patch.object(webapp, "read_env", return_value={"WEBUI_AUTH_ENABLED": "true"}), patch.object(backend, "export_paper_reports") as export, TestClient(webapp.app) as client:
        assert client.post("/api/papers/export", json={"entity_ids": [ids["one"]]}).status_code in [401, 503]
        export.assert_not_called()
