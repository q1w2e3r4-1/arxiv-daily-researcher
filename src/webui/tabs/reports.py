"""Reports Viewer tab for the Streamlit config panel."""

from __future__ import annotations

import datetime
import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, NamedTuple, Optional

import streamlit as st
import streamlit.components.v1 as components

from webui.i18n import t

# project root: tabs/ -> webui/ -> src/ -> project_root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPORTS_DIR = _PROJECT_ROOT / "data" / "reports"
_DAILY_RESEARCH_DB = _PROJECT_ROOT / "data" / "daily_research" / "daily_research.db"

_SEL_KEY = "rsel"  # prefix for all selectbox session-state keys
_PREVIEW_KEY = "preview_report"
_FORCE_LATEST_KEY = "reports_force_latest"

# ArXiv 来源标识（用于非 ArXiv 过滤）
_ARXIV_SOURCES = {"ARXIV", "arxiv"}


# ─── data structures ──────────────────────────────────────────────────────────


class ReportFile(NamedTuple):
    path: Path
    display: str  # human-friendly label shown in UI
    source: str  # uppercase source name / keyword slug / "keyword_trend"
    report_type: str  # "daily" | "trend" | "keyword_trend"
    date_key: str  # YYYY-MM-DD 日期字符串，用于前后天导航


# ─── label formatting ─────────────────────────────────────────────────────────


def _fmt_daily(stem: str) -> str:
    """ARXIV_Report_2026-03-10_12-27-47  →  2026-03-10  12:27:47"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})$", stem)
    if m:
        return f"{m.group(1)}  {m.group(2).replace('-', ':')}"
    return stem


def _extract_date_key(stem: str) -> str:
    """从报告文件名中提取 YYYY-MM-DD 作为导航键。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else ""


def _fmt_trend(stem: str) -> str:
    """2025-03-10_2026-03-10  →  2025-03-10 → 2026-03-10"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", stem)
    if m:
        return f"{m.group(1)} → {m.group(2)}"
    return stem


def _fmt_kw(stem: str) -> str:
    """keyword_trends_2026-03-09  →  2026-03-09"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", stem)
    return m.group(1) if m else stem


# ─── discovery ────────────────────────────────────────────────────────────────


def _discover_reports() -> dict[str, list[ReportFile]]:
    """Scan data/reports/ and return three lists, each newest-first."""
    result: dict[str, list[ReportFile]] = {
        "daily": [],
        "trend": [],
        "keyword_trend": [],
    }

    # daily_research/html/{source}/*.html
    daily_html = _REPORTS_DIR / "daily_research" / "html"
    if daily_html.exists():
        for src_dir in daily_html.iterdir():
            if src_dir.is_dir():
                src = src_dir.name.upper()
                for f in src_dir.glob("*.html"):
                    result["daily"].append(
                        ReportFile(f, _fmt_daily(f.stem), src, "daily", _extract_date_key(f.stem))
                    )
        result["daily"].sort(key=lambda r: r.path.stat().st_mtime, reverse=True)

    # trend_research/html/{keyword-slug}/*.html
    trend_html = _REPORTS_DIR / "trend_research" / "html"
    if trend_html.exists():
        for kw_dir in trend_html.iterdir():
            if kw_dir.is_dir():
                slug = kw_dir.name
                for f in kw_dir.glob("*.html"):
                    result["trend"].append(
                        ReportFile(f, _fmt_trend(f.stem), slug, "trend", _extract_date_key(f.stem))
                    )
        result["trend"].sort(key=lambda r: r.path.stat().st_mtime, reverse=True)

    # keyword_trend/html/*.html
    kw_html = _REPORTS_DIR / "keyword_trend" / "html"
    if kw_html.exists():
        for f in sorted(kw_html.glob("*.html"), reverse=True):
            result["keyword_trend"].append(
                ReportFile(
                    f, _fmt_kw(f.stem), "keyword_trend", "keyword_trend", _extract_date_key(f.stem)
                )
            )

    return result


def _load_trend_metadata(html_path: Path) -> dict | None:
    md_dir = html_path.parent.parent.parent / "markdown" / html_path.parent.name
    meta_path = md_dir / f"{html_path.stem}_metadata.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ─── file browser helpers ─────────────────────────────────────────────────────


def _sel_key(rtype: str, group: str) -> str:
    return f"{_SEL_KEY}_{rtype}_{group}"


def _make_on_change(key: str, by_display: dict[str, ReportFile]):
    """Return an on_change callback that updates preview_report."""

    def _cb():
        chosen = st.session_state.get(key)
        if chosen in by_display:
            st.session_state[_PREVIEW_KEY] = by_display[chosen]

    return _cb


def _render_group_selectbox(rtype: str, group: str, reports: list[ReportFile]) -> None:
    """Render one selectbox for a source/slug group; updates preview on change."""
    by_display = {r.display: r for r in reports}
    labels = [r.display for r in reports]
    key = _sel_key(rtype, group)

    # Auto-set preview if nothing selected yet
    if _PREVIEW_KEY not in st.session_state and reports:
        st.session_state[_PREVIEW_KEY] = reports[0]

    st.selectbox(
        f"**{group}** ({len(labels)})",
        labels,
        key=key,
        on_change=_make_on_change(key, by_display),
    )
    # Button to explicitly load this selectbox's current selection into preview
    if st.button(t("reports_preview_btn"), key=f"btn_{key}", use_container_width=True):
        chosen = st.session_state.get(key)
        if chosen in by_display:
            st.session_state[_PREVIEW_KEY] = by_display[chosen]
            st.rerun()


def _filter_visible_reports(
    all_reports: dict[str, list[ReportFile]],
    show_non_arxiv: bool,
) -> dict[str, list[ReportFile]]:
    """返回当前界面实际可见的报告集合。"""
    daily_reports = all_reports.get("daily", [])
    if not show_non_arxiv:
        daily_reports = [r for r in daily_reports if r.source.upper() in _ARXIV_SOURCES]

    return {
        "daily": daily_reports,
        "trend": all_reports.get("trend", []),
        "keyword_trend": all_reports.get("keyword_trend", []),
    }


def _latest_visible_report(visible_reports: dict[str, list[ReportFile]]) -> Optional[ReportFile]:
    """从当前可见报告中找出修改时间最新的一份。"""
    candidates = [r for reports in visible_reports.values() for r in reports]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.path.stat().st_mtime)


def _render_category_col(
    rtype: str,
    reports: list[ReportFile],
    header: str,
) -> None:
    """渲染一个报告类型列（daily / trend / keyword_trend）。"""
    count = len(reports)
    st.markdown(
        f"**{header}**<br>"
        f"<span style='color:#888;font-size:0.82em'>{count} {t('reports_count_unit')}</span>",
        unsafe_allow_html=True,
    )

    if not reports:
        st.caption(t("reports_empty_type"))
        return

    if rtype == "keyword_trend":
        _render_group_selectbox(rtype, "keyword_trend", reports)
    else:
        # Group by source / keyword slug
        groups = sorted({r.source for r in reports})
        for grp in groups:
            grp_reports = [r for r in reports if r.source == grp]
            _render_group_selectbox(rtype, grp, grp_reports)


# ─── navigation helpers ───────────────────────────────────────────────────────


def _find_adjacent_report(
    current: ReportFile,
    all_reports: dict[str, list[ReportFile]],
    direction: int,  # -1 = 前一天, +1 = 后一天
) -> Optional[ReportFile]:
    """
    在同一数据源（source）内寻找相邻「日期」的报告。

    修复说明：原外用 current_dates.index() 会在同一天有多份报告时
    永远返回第一条（导致「后一天」在同日期内打转而不前进）。
    现在改为基于唯一日期列表寻找，返回目标日期中最新的报告。
    """
    if not current.date_key:
        return None

    # 同类型、同 source 的所有报告
    same_source = [
        r
        for r in all_reports.get(current.report_type, [])
        if r.source == current.source and r.date_key
    ]
    if not same_source:
        return None

    # 唯一日期列表（升序）
    unique_dates = sorted({r.date_key for r in same_source})
    if current.date_key not in unique_dates:
        return None

    date_idx = unique_dates.index(current.date_key)
    new_date_idx = date_idx + direction
    if not (0 <= new_date_idx < len(unique_dates)):
        return None  # 已是最早/最新日期

    target_date = unique_dates[new_date_idx]
    # 返回目标日期内最新的一份报告（按文件修改时间）
    candidates = [r for r in same_source if r.date_key == target_date]
    return max(candidates, key=lambda r: r.path.stat().st_mtime)


# ─── preview ──────────────────────────────────────────────────────────────────


def _render_preview(report: ReportFile, all_reports: dict[str, list[ReportFile]]) -> None:
    """渲染报告预览区：文件信息栏 + 前/后天导航 + 固定 800px HTML 预览。"""

    # File info bar
    stat = report.path.stat()
    size_kb = stat.st_size / 1024
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    type_cn = {
        "daily": t("rtype_daily"),
        "trend": t("rtype_trend"),
        "keyword_trend": t("rtype_keyword_trend"),
    }.get(report.report_type, report.report_type)

    st.caption(
        f"**{type_cn}** · `{report.source}` · `{report.path.name}` · "
        f"{size_kb:.1f} KB · {t('reports_mtime')}: {mtime}"
    )

    # Trend metadata
    if report.report_type == "trend":
        meta = _load_trend_metadata(report.path)
        if meta:
            with st.expander(t("reports_meta_expander"), expanded=False):
                cols = st.columns(3)
                if "keyword" in meta:
                    cols[0].metric(t("meta_keyword"), meta["keyword"])
                if "date_from" in meta and "date_to" in meta:
                    cols[1].metric(t("meta_date_range"), f"{meta['date_from']} → {meta['date_to']}")
                if "total_papers" in meta:
                    cols[2].metric(t("meta_papers"), meta["total_papers"])

    # ── 前/后天导航按钮（仅 daily 类型显示，且只在同一 source 内跳转）──
    if report.report_type == "daily":
        prev_report = _find_adjacent_report(report, all_reports, -1)
        next_report = _find_adjacent_report(report, all_reports, +1)

        nav_col1, nav_spacer, nav_col2 = st.columns([1, 4, 1])
        with nav_col1:
            if prev_report:
                if st.button(
                    t("report_prev_day"),
                    key="nav_prev",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state[_PREVIEW_KEY] = prev_report
                    st.rerun()
            else:
                st.button(
                    t("report_prev_day"),
                    key="nav_prev",
                    disabled=True,
                    use_container_width=True,
                    help=t("report_no_prev"),
                )
        with nav_col2:
            if next_report:
                if st.button(
                    t("report_next_day"),
                    key="nav_next",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state[_PREVIEW_KEY] = next_report
                    st.rerun()
            else:
                st.button(
                    t("report_next_day"),
                    key="nav_next",
                    disabled=True,
                    use_container_width=True,
                    help=t("report_no_next"),
                )

    # ── HTML 预览（固定 800px 高度）──
    try:
        html_content = report.path.read_text(encoding="utf-8")
        components.html(html_content, height=800, scrolling=True)
    except Exception as e:
        st.error(f"{t('reports_load_error')}: {e}")


def _get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DAILY_RESEARCH_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=30)
def _query_daily_window(date_from: datetime.date, date_to: datetime.date, include_rejected: bool) -> list[dict[str, Any]]:
    if not _DAILY_RESEARCH_DB.exists():
        return []

    query = """
        SELECT source, paper_id, title, published_date, url, pdf_url, doi, journal,
               is_qualified, total_score, passing_score, scoring_method,
               authors_json, categories_json, abstract, abstract_cn, score_json,
               analysis_json, metadata_json
        FROM daily_papers
        WHERE completed_at IS NOT NULL
          AND published_date IS NOT NULL
          AND substr(published_date, 1, 10) >= ?
          AND substr(published_date, 1, 10) <= ?
    """
    params: list[Any] = [date_from.isoformat(), date_to.isoformat()]
    if not include_rejected:
        query += " AND is_qualified = 1"
    query += " ORDER BY COALESCE(total_score, 0) DESC, published_date DESC, source ASC, paper_id ASC"

    with _get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    papers: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        score = _load_score_json(row_dict.get("score_json"))
        if not score:
            continue
        papers.append(
            {
                "source": row_dict.get("source") or "",
                "paper_id": row_dict.get("paper_id") or "",
                "title": row_dict.get("title") or "Untitled",
                "published": (row_dict.get("published_date") or "")[:10] or "N/A",
                "url": row_dict.get("url") or "",
                "pdf_url": row_dict.get("pdf_url") or "",
                "doi": row_dict.get("doi") or "",
                "journal": row_dict.get("journal") or "",
                "authors": _format_authors(row_dict.get("authors_json")),
                "categories": _load_json_list(row_dict.get("categories_json")),
                "abstract": (row_dict.get("abstract") or "").strip(),
                "abstract_cn": (row_dict.get("abstract_cn") or "").strip(),
                "score": score,
                "analysis": _load_json_dict(row_dict.get("analysis_json")),
            }
        )

    return papers


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _load_json_list(raw: str | None) -> list[str]:
    value = _json_loads(raw, [])
    return value if isinstance(value, list) else []


def _load_json_dict(raw: str | None) -> dict[str, Any]:
    value = _json_loads(raw, {})
    return value if isinstance(value, dict) else {}


def _load_score_json(raw: str | None) -> dict[str, Any]:
    value = _json_loads(raw, None)
    return value if isinstance(value, dict) else {}


def _format_authors(raw: str | None) -> str:
    authors = _load_json_list(raw)
    return ", ".join(str(a).strip() for a in authors if str(a).strip())


def _escape(text: Any) -> str:
    if text is None:
        return ""
    return html.escape(str(text))


def _render_analysis_html(analysis: dict[str, Any]) -> str:
    if not analysis:
        return ""

    parts = ["<details><summary>深度分析</summary><div class=\"analysis-content\">"]
    for key, value in analysis.items():
        if value in (None, "", [], {}):
            continue
        label = _escape(str(key).replace("_", " ").title())
        if isinstance(value, list):
            parts.append(f"<p><strong>{label}:</strong></p><ul>")
            for item in value:
                parts.append(f"<li>{_escape(item)}</li>")
            parts.append("</ul>")
        elif isinstance(value, dict):
            parts.append(f"<p><strong>{label}:</strong></p><ul>")
            for k, v in value.items():
                parts.append(f"<li><strong>{_escape(k)}:</strong> {_escape(v)}</li>")
            parts.append("</ul>")
        else:
            parts.append(f"<p><strong>{label}:</strong> {_escape(value)}</p>")
    parts.append("</div></details>")
    return "".join(parts)


def _render_db_window_html(title: str, papers: list[dict[str, Any]]) -> str:
    qualified_count = sum(1 for p in papers if p["score"].get("is_qualified"))
    analyzed_count = sum(1 for p in papers if p.get("analysis"))
    pass_rate = (qualified_count / len(papers) * 100) if papers else 0

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:16px;color:#111827;background:#fff;}"
        ".stats-bar{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 24px;}"
        ".stat{background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px;min-width:110px;}"
        ".num{font-size:28px;font-weight:700;}"
        ".label{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;}"
        ".card{border:1px solid #e5e7eb;border-left-width:6px;border-radius:12px;padding:16px;margin:0 0 16px;background:#fff;}"
        ".card.pass{border-left-color:#16a34a;background:#f0fdf4;}"
        ".card.fail{border-left-color:#dc2626;background:#fef2f2;}"
        ".card-title{font-size:18px;font-weight:700;margin-bottom:8px;display:flex;justify-content:space-between;gap:12px;align-items:flex-start;}"
        ".card-title a{text-decoration:none;color:#111827;}"
        ".badge{font-size:12px;font-weight:700;border-radius:999px;padding:4px 10px;white-space:nowrap;}"
        ".badge.pass{background:#dcfce7;color:#166534;}"
        ".badge.fail{background:#fee2e2;color:#991b1b;}"
        ".field{margin:4px 0;color:#374151;}"
        ".field-label{font-weight:600;color:#111827;}"
        ".score{font-weight:700;}"
        ".summary{margin-top:10px;line-height:1.6;white-space:pre-wrap;}"
        ".muted{color:#6b7280;}"
        ".analysis-content{margin-top:8px;}"
        "details{margin-top:12px;}"
        "</style>",
        "</head><body>",
        f"<h1>{_escape(title)}</h1>",
        f'<p class="muted">Generated: {_escape(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>',
        '<div class="stats-bar">',
        f'<div class="stat"><div class="num">{len(papers)}</div><div class="label">Total</div></div>',
        f'<div class="stat"><div class="num">{qualified_count}</div><div class="label">Qualified</div></div>',
        f'<div class="stat"><div class="num">{len(papers) - qualified_count}</div><div class="label">Rejected</div></div>',
        f'<div class="stat"><div class="num">{analyzed_count}</div><div class="label">Analyzed</div></div>',
        f'<div class="stat"><div class="num">{pass_rate:.0f}%</div><div class="label">Pass Rate</div></div>',
        "</div>",
    ]

    for idx, paper in enumerate(papers, 1):
        score = paper["score"]
        is_qualified = bool(score.get("is_qualified"))
        cls = "pass" if is_qualified else "fail"
        badge_text = "PASS" if is_qualified else "FAIL"
        title_html = _escape(paper["title"])
        url = paper.get("url") or ""
        if url:
            title_html = f'<a href="{_escape(url)}" target="_blank">{idx}. {title_html}</a>'
        else:
            title_html = f"{idx}. {title_html}"

        parts.append(f'<div class="card {cls}">')
        parts.append(
            f'<div class="card-title">{title_html}<span class="badge {cls}">{badge_text}</span></div>'
        )
        parts.append(
            f'<div class="field"><span class="field-label">Score:</span> '
            f'<span class="score">{float(score.get("total_score", 0)):.1f}</span> / {float(score.get("passing_score", 0)):.1f}</div>'
        )
        if paper.get("authors"):
            parts.append(
                f'<div class="field"><span class="field-label">Authors:</span> {_escape(paper["authors"])}</div>'
            )
        parts.append(
            f'<div class="field"><span class="field-label">Published:</span> {_escape(paper.get("published", "N/A"))}</div>'
        )
        parts.append(
            f'<div class="field"><span class="field-label">Source:</span> {_escape((paper.get("source") or "").upper())}</div>'
        )

        judgments = score.get("model_judgments") or []
        if judgments:
            model_scores = " | ".join(
                f"{row.get('model', '')}: {float(row.get('final_score', 0)):.1f}" for row in judgments
            )
            if model_scores:
                parts.append(
                    f'<div class="field"><span class="field-label">Model Scores:</span> {_escape(model_scores)}</div>'
                )

        reasoning = (score.get("reasoning") or "").strip()
        if reasoning:
            parts.append(f'<div class="summary"><strong>Reasoning:</strong> {_escape(reasoning)}</div>')

        visible_summary = (paper.get("abstract_cn") or "").strip() if is_qualified else ""
        if not visible_summary:
            visible_summary = (paper.get("abstract") or "").strip()
        if visible_summary:
            parts.append(f'<div class="summary"><strong>摘要:</strong> {_escape(visible_summary)}</div>')

        analysis_html = _render_analysis_html(paper.get("analysis") or {})
        if analysis_html:
            parts.append(analysis_html)

        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_db_window_summary() -> None:
    st.markdown(
        f'<p class="section-title">🗂️ {t("reports_db_window_title")}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="hint-text">{t("reports_db_window_hint")}</p>',
        unsafe_allow_html=True,
    )

    if not _DAILY_RESEARCH_DB.exists():
        st.info(t("reports_db_missing"))
        return

    today = datetime.date.today()
    default_from = today - datetime.timedelta(days=6)

    col_from, col_to, col_toggle = st.columns([1.2, 1.2, 1])
    with col_from:
        date_from = st.date_input(
            t("reports_db_date_from"),
            value=default_from,
            key="reports_db_date_from",
        )
    with col_to:
        date_to = st.date_input(
            t("reports_db_date_to"),
            value=today,
            key="reports_db_date_to",
        )
    with col_toggle:
        include_rejected = st.toggle(
            t("reports_db_include_rejected"),
            value=False,
            key="reports_db_include_rejected",
            help=t("reports_db_include_rejected_help"),
        )

    if date_from > date_to:
        st.error(t("reports_db_invalid_range"))
        return

    papers = _query_daily_window(date_from, date_to, include_rejected)
    if not papers:
        st.info(t("reports_db_empty"))
        return

    qualified_count = sum(1 for p in papers if p["score"].get("is_qualified"))
    rejected_count = len(papers) - qualified_count
    analysis_count = sum(1 for p in papers if p.get("analysis"))

    metric_cols = st.columns(4)
    metric_cols[0].metric(t("reports_db_metric_total"), len(papers))
    metric_cols[1].metric(t("reports_db_metric_qualified"), qualified_count)
    metric_cols[2].metric(t("reports_db_metric_rejected"), rejected_count)
    metric_cols[3].metric(t("reports_db_metric_analyzed"), analysis_count)

    title = f"{t('reports_db_summary_title_prefix')} {date_from.isoformat()} → {date_to.isoformat()}"
    html_content = _render_db_window_html(title, papers)
    components.html(html_content, height=800, scrolling=True)


# ─── main render ──────────────────────────────────────────────────────────────


def render(_env_values: dict, _config_values: dict) -> None:
    """渲染报告查看 Tab。"""

    st.markdown(
        f'<p class="hint-text">{t("reports_hint")}</p>',
        unsafe_allow_html=True,
    )

    _render_db_window_summary()
    st.divider()

    # 工具栏：刷新 + 非ArXiv过滤开关
    col_refresh, col_filter, _ = st.columns([1, 2, 3])
    with col_refresh:
        if st.button(t("reports_refresh"), use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith(_SEL_KEY) or k == _PREVIEW_KEY:
                    del st.session_state[k]
            st.session_state[_FORCE_LATEST_KEY] = True
            st.rerun()
    with col_filter:
        show_non_arxiv = st.toggle(
            t("report_show_non_arxiv"),
            value=False,
            key="reports_show_non_arxiv",
            help="开启后显示所有来源；关闭后仅显示 ArXiv 来源的每日研究报告",
        )

    st.divider()

    all_reports = _discover_reports()
    visible_reports = _filter_visible_reports(all_reports, show_non_arxiv)
    total = sum(len(v) for v in visible_reports.values())

    if total == 0:
        st.info(t("reports_empty"))
        st.caption(f"📂 {t('reports_dir_label')}: `{_REPORTS_DIR}`")
        return

    latest_visible = _latest_visible_report(visible_reports)
    current_preview: ReportFile | None = st.session_state.get(_PREVIEW_KEY)
    visible_paths = {str(r.path) for reports in visible_reports.values() for r in reports}
    force_latest = st.session_state.pop(_FORCE_LATEST_KEY, False)

    if force_latest or current_preview is None or str(current_preview.path) not in visible_paths:
        if latest_visible is not None:
            st.session_state[_PREVIEW_KEY] = latest_visible

    # ── 三列报告浏览器 ──────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)

    with c1:
        _render_category_col(
            "daily",
            visible_reports["daily"],
            f"📅 {t('rtype_daily')}",
        )

    with c2:
        _render_category_col(
            "trend",
            visible_reports["trend"],
            f"🔬 {t('rtype_trend')}",
        )

    with c3:
        _render_category_col(
            "keyword_trend",
            visible_reports["keyword_trend"],
            f"📈 {t('rtype_keyword_trend')}",
        )

    # ── 预览区 ────────────────────────────────────────────────────────────
    report: ReportFile | None = st.session_state.get(_PREVIEW_KEY)
    if report is None:
        return

    st.divider()
    _render_preview(report, visible_reports)


def collect(_env_values: dict, _config_values: dict) -> dict:
    """报告查看 Tab 无配置需保存，返回空字典。"""
    return {}
