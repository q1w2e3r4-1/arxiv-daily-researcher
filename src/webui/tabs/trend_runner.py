"""趋势分析 Tab — 配置并启动研究趋势分析任务。"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from webui.i18n import t, _TRANSLATIONS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_MAIN_PY = _PROJECT_ROOT / "main.py"
_LOCK_DIR = _PROJECT_ROOT / "data" / "run"

# 所有可用的趋势分析技能
ALL_TREND_SKILL_IDS = [
    "hot_topics",
    "time_evolution",
    "key_researchers",
    "research_gaps",
    "methodology_trends",
    "comprehensive_analysis",
]


def _get_trend_lock_files() -> list[Path]:
    if not _LOCK_DIR.exists():
        return []
    return list(_LOCK_DIR.glob("trend_research_*.lock"))


def _is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_pid_from_lock(lock_path: Path):
    try:
        content = lock_path.read_text(encoding="utf-8")
        m = re.search(r"PID=(\d+)", content)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _skill_label(skill_id: str) -> str:
    """获取技能的当前语言标签。"""
    lang = st.session_state.get("lang", "zh")
    entry = _TRANSLATIONS.get(f"skill_{skill_id}", {})
    return entry.get(lang, entry.get("en", skill_id.replace("_", " ").title()))


def render(_env_values: dict, config_values: dict) -> None:
    """渲染趋势分析 Tab。"""
    from utils.config_io import flatten_config_dict

    flat = flatten_config_dict(config_values) if config_values else {}

    st.markdown(
        f'<p class="section-title">{t("trend_runner_title")}</p>',
        unsafe_allow_html=True,
    )

    # ── 1. 分析参数 ──────────────────────────────────────────────────────────
    st.markdown(f"#### 🔍 {t('tr_section_params')}")

    keywords_input = st.text_input(
        t("trend_keywords_label"),
        value="",
        key="tr_keywords",
        placeholder=t("tr_keywords_placeholder"),
        help=t("trend_keywords_help"),
    )

    col_d1, col_d2 = st.columns(2)
    default_days = flat.get("trend_default_date_range_days", 365)
    with col_d1:
        date_from = st.date_input(
            t("trend_date_from"),
            value=date.today() - timedelta(days=default_days),
            key="tr_date_from",
        )
    with col_d2:
        date_to = st.date_input(
            t("trend_date_to"),
            value=date.today(),
            key="tr_date_to",
        )

    categories_input = st.text_input(
        t("trend_categories_label"),
        value="",
        key="tr_categories",
        placeholder=t("tr_categories_placeholder"),
        help=t("trend_categories_help"),
    )

    st.divider()

    # ── 2. 分析配置 ──────────────────────────────────────────────────────────
    st.markdown(f"#### ⚙️ {t('trend_config_title')}")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        sort_options = ["ascending", "descending"]
        current_sort = flat.get("trend_sort_order", "ascending")
        st.selectbox(
            t("trend_sort_label"),
            options=sort_options,
            index=sort_options.index(current_sort) if current_sort in sort_options else 0,
            key="trend_sort_order",
        )
        st.number_input(
            t("tr_default_date_range_days_label"),
            min_value=30,
            max_value=3650,
            value=flat.get("trend_default_date_range_days", 365),
            key="trend_default_date_range_days",
            help=t("tr_default_date_range_days_help"),
        )

    with col_c2:
        st.number_input(
            t("trend_max_results_label"),
            min_value=10,
            max_value=5000,
            value=flat.get("trend_max_results", 500),
            key="trend_max_results",
        )
        pos_options = ["beginning", "end"]
        current_pos = flat.get("trend_report_position", "end")
        st.selectbox(
            t("trend_report_position_label"),
            options=pos_options,
            index=pos_options.index(current_pos) if current_pos in pos_options else 1,
            key="trend_report_position",
        )

    col_c3, col_c4 = st.columns(2)
    with col_c3:
        st.toggle(
            t("trend_generate_tldr_label"),
            value=flat.get("trend_generate_tldr", True),
            key="trend_generate_tldr",
        )
    with col_c4:
        st.number_input(
            t("trend_tldr_batch_label"),
            min_value=1,
            max_value=50,
            value=flat.get("trend_tldr_batch_size", 10),
            key="trend_tldr_batch_size",
        )

    # 输出格式
    output_formats = flat.get("trend_output_formats", ["markdown", "html"])
    fmt_options = ["markdown", "html"]
    st.multiselect(
        t("trend_output_formats_label"),
        options=fmt_options,
        default=[f for f in output_formats if f in fmt_options],
        key="trend_output_formats",
    )

    # 启用的技能
    st.markdown(f"**{t('trend_skills_label')}**")
    current_skills = flat.get("trend_enabled_skills", ALL_TREND_SKILL_IDS)
    skill_cols = st.columns(3)
    for i, skill_id in enumerate(ALL_TREND_SKILL_IDS):
        with skill_cols[i % 3]:
            st.checkbox(
                _skill_label(skill_id),
                value=skill_id in current_skills,
                key=f"skill_{skill_id}",
            )

    st.divider()

    # ── 3. 运行控制 ──────────────────────────────────────────────────────────
    st.markdown(f"#### 🚀 {t('tr_section_run_control')}")

    # 当前趋势分析进程状态
    trend_locks = _get_trend_lock_files()
    if trend_locks:
        st.info(t("tr_locks_found").format(n=len(trend_locks)))
        for lock in trend_locks:
            pid = _read_pid_from_lock(lock)
            is_running = pid and _is_pid_running(pid)
            status = f"🟢 {t('rm_status_running')}" if is_running else f"🔴 {t('rm_status_stopped')}"
            st.caption(f"{status} — `{lock.name}` PID={pid or t('rm_no_pid')}")

    col_run, col_stop, _ = st.columns([1, 1, 3])

    with col_run:
        run_clicked = st.button(
            t("trend_run_btn"),
            key="tr_run_btn",
            type="primary",
            use_container_width=True,
        )

    with col_stop:
        stop_clicked = st.button(
            t("tr_stop_btn_label"),
            key="tr_stop_btn",
            type="secondary",
            use_container_width=True,
        )

    # 处理停止
    if stop_clicked:
        trend_locks = _get_trend_lock_files()
        stopped = 0
        for lock in trend_locks:
            pid = _read_pid_from_lock(lock)
            if pid and _is_pid_running(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                    st.info(t("tr_stop_signal_sent").format(pid=pid, name=lock.name))
                    stopped += 1
                except Exception as e:
                    st.error(t("tr_stop_failed").format(pid=pid, err=e))
        if stopped == 0:
            st.info(t("tr_no_running_trend"))
        else:
            time.sleep(0.5)
            st.rerun()

    # 处理运行
    if run_clicked:
        if not keywords_input.strip():
            st.error(t("tr_err_no_keywords"))
        elif date_from > date_to:
            st.error(t("tr_err_date_range"))
        else:
            cmd = [
                sys.executable,
                str(_MAIN_PY),
                "--mode", "trend_research",
                "--keywords", keywords_input.strip(),
                "--date-from", str(date_from),
                "--date-to", str(date_to),
                "--max-results", str(st.session_state.get("trend_max_results", 500)),
                "--sort-order", st.session_state.get("trend_sort_order", "ascending"),
            ]
            cats = categories_input.strip()
            if cats:
                for cat in cats.split():
                    cmd += ["--categories", cat]

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(_PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                st.success(t("tr_started").format(pid=proc.pid))
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(t("tr_start_failed").format(err=e))


def collect(_env_values: dict, _config_values: dict) -> dict:
    """从 session_state 收集趋势分析配置，保存到 config.json。"""
    enabled_skills = [
        skill_id
        for skill_id in ALL_TREND_SKILL_IDS
        if st.session_state.get(f"skill_{skill_id}", False)
    ]

    return {
        "trend_default_date_range_days": st.session_state.get("trend_default_date_range_days", 365),
        "trend_max_results": st.session_state.get("trend_max_results", 500),
        "trend_sort_order": st.session_state.get("trend_sort_order", "ascending"),
        "trend_report_position": st.session_state.get("trend_report_position", "end"),
        "trend_generate_tldr": st.session_state.get("trend_generate_tldr", True),
        "trend_tldr_batch_size": st.session_state.get("trend_tldr_batch_size", 10),
        "trend_output_formats": st.session_state.get("trend_output_formats", ["markdown", "html"]),
        "trend_enabled_skills": enabled_skills,
    }
