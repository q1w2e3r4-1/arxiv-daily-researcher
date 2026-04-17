"""Advanced Settings tab for the Streamlit config panel."""

import streamlit as st
from webui.i18n import t


ALL_TREND_SKILL_IDS = [
    "temporal_evolution",
    "hot_topics",
    "key_authors",
    "research_gaps",
    "methodology_trends",
    "comprehensive_analysis",
]


def render(_env_values: dict, config_values: dict):
    """Render the Advanced Settings tab."""

    flat = config_values

    # ---- PDF Parser ----
    st.markdown(f'<p class="section-title">{t("pdf_parser_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("pdf_parser_hint")}</p>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        mode_options = ["mineru", "pymupdf"]
        current_mode = flat.get("pdf_parser_mode", "mineru")
        st.selectbox(
            t("parser_mode_label"),
            options=mode_options,
            index=mode_options.index(current_mode) if current_mode in mode_options else 0,
            key="pdf_parser_mode",
            help=t("parser_mode_help"),
        )
    with col2:
        version_options = ["pipeline", "vlm"]
        current_ver = flat.get("mineru_model_version", "pipeline")
        st.selectbox(
            t("mineru_version_label"),
            options=version_options,
            index=version_options.index(current_ver) if current_ver in version_options else 0,
            key="mineru_model_version",
            help=t("mineru_version_help"),
        )

    st.divider()

    # ---- Concurrency ----
    st.markdown(f'<p class="section-title">{t("concurrency_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("concurrency_hint")}</p>', unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.toggle(
            t("enable_concurrency"),
            value=flat.get("concurrency_enabled", False),
            key="concurrency_enabled",
        )
    with col4:
        st.number_input(
            t("worker_threads_label"),
            min_value=1,
            max_value=10,
            value=flat.get("concurrency_workers", 3),
            key="concurrency_workers",
            help=t("worker_threads_help"),
        )

    st.divider()

    # ---- Report & Token Tracking ----
    st.markdown(
        f'<p class="section-title">{t("advanced_reports_title")}</p>',
        unsafe_allow_html=True,
    )

    col5, col6, col7 = st.columns(3)
    with col5:
        st.toggle(
            t("html_reports_label"),
            value=flat.get("enable_html_report", True),
            key="enable_html_report",
        )
    with col6:
        st.toggle(
            t("token_tracking_label"),
            value=flat.get("token_tracking_enabled", True),
            key="token_tracking_enabled",
        )
    with col7:
        st.toggle(
            t("auto_update_label"),
            value=flat.get("auto_update_enabled", True),
            key="auto_update_enabled",
        )

    st.divider()

    # ---- Keyword Tracker ----
    st.markdown(f'<p class="section-title">{t("kw_tracker_title")}</p>', unsafe_allow_html=True)

    st.toggle(
        t("enable_kw_tracker"),
        value=flat.get("keyword_tracker_enabled", True),
        key="keyword_tracker_enabled",
    )

    with st.expander(t("kw_tracker_expander"), expanded=False):
        col8, col9 = st.columns(2)
        with col8:
            st.toggle(
                t("ai_normalization_label"),
                value=flat.get("keyword_normalization_enabled", True),
                key="keyword_normalization_enabled",
            )
            st.number_input(
                t("normalization_batch_label"),
                min_value=5,
                max_value=100,
                value=flat.get("keyword_normalization_batch_size", 25),
                key="keyword_normalization_batch_size",
            )
        with col9:
            st.number_input(
                t("trend_view_days_label"),
                min_value=7,
                max_value=365,
                value=flat.get("keyword_trend_default_days", 30),
                key="keyword_trend_default_days",
            )

        col10, col11 = st.columns(2)
        with col10:
            st.number_input(
                t("bar_chart_top_n_label"),
                min_value=5,
                max_value=50,
                value=flat.get("keyword_chart_top_n", 15),
                key="keyword_chart_top_n",
            )
        with col11:
            st.number_input(
                t("trend_chart_top_n_label"),
                min_value=3,
                max_value=20,
                value=flat.get("keyword_trend_top_n", 5),
                key="keyword_trend_top_n",
            )

        st.toggle(
            t("enable_trend_reports_label"),
            value=flat.get("keyword_report_enabled", True),
            key="keyword_report_enabled",
        )

        freq_options = ["daily", "weekly", "monthly", "always"]
        current_freq = flat.get("keyword_report_frequency", "weekly")
        st.selectbox(
            t("report_frequency_label"),
            options=freq_options,
            index=freq_options.index(current_freq) if current_freq in freq_options else 1,
            key="keyword_report_frequency",
        )

    st.divider()

    # ---- Retry ----
    st.markdown(f'<p class="section-title">{t("retry_title")}</p>', unsafe_allow_html=True)

    col12, col13, col14 = st.columns(3)
    with col12:
        st.number_input(
            t("max_retries_label"),
            min_value=1,
            max_value=10,
            value=flat.get("retry_max_attempts", 3),
            key="retry_max_attempts",
        )
    with col13:
        st.number_input(
            t("min_wait_label"),
            min_value=1,
            max_value=60,
            value=flat.get("retry_min_wait", 2),
            key="retry_min_wait",
        )
    with col14:
        st.number_input(
            t("max_wait_label"),
            min_value=5,
            max_value=300,
            value=flat.get("retry_max_wait", 30),
            key="retry_max_wait",
        )

    st.number_input(
        t("run_lock_max_age_label"),
        min_value=1,
        max_value=168,
        value=flat.get("run_lock_max_age_hours", 12),
        key="run_lock_max_age_hours",
        help=t("run_lock_max_age_help"),
    )

    col15, col16 = st.columns(2)
    with col15:
        rot_options = ["time", "size"]
        current_rot = flat.get("log_rotation_type", "time")
        st.selectbox(
            t("log_rotation_label"),
            options=rot_options,
            index=rot_options.index(current_rot) if current_rot in rot_options else 0,
            key="log_rotation_type",
        )
    with col16:
        st.number_input(
            t("log_retention_label"),
            min_value=1,
            max_value=365,
            value=flat.get("log_keep_days", 30),
            key="log_keep_days",
        )

    # 趋势分析设置已移至「趋势分析」 Tab，请在趋势分析 Tab 中配置。


def collect(_env_values: dict, _config_values: dict) -> dict:
    """从 session_state 收集当前值，返回 config 更新字典。"""
    # 注意：趋势分析的配置已移至 trend_runner.py，这里不再收集趋势分析相关设置。
    return {
        "pdf_parser_mode": st.session_state.get("pdf_parser_mode", "mineru"),
        "mineru_model_version": st.session_state.get("mineru_model_version", "pipeline"),
        "concurrency_enabled": st.session_state.get("concurrency_enabled", False),
        "concurrency_workers": st.session_state.get("concurrency_workers", 3),
        "enable_html_report": st.session_state.get("enable_html_report", True),
        "token_tracking_enabled": st.session_state.get("token_tracking_enabled", True),
        "auto_update_enabled": st.session_state.get("auto_update_enabled", True),
        "keyword_tracker_enabled": st.session_state.get("keyword_tracker_enabled", True),
        "keyword_normalization_enabled": st.session_state.get(
            "keyword_normalization_enabled", True
        ),
        "keyword_normalization_batch_size": st.session_state.get(
            "keyword_normalization_batch_size", 25
        ),
        "keyword_trend_default_days": st.session_state.get("keyword_trend_default_days", 30),
        "keyword_chart_top_n": st.session_state.get("keyword_chart_top_n", 15),
        "keyword_trend_top_n": st.session_state.get("keyword_trend_top_n", 5),
        "keyword_report_enabled": st.session_state.get("keyword_report_enabled", True),
        "keyword_report_frequency": st.session_state.get("keyword_report_frequency", "weekly"),
        "retry_max_attempts": st.session_state.get("retry_max_attempts", 3),
        "retry_min_wait": st.session_state.get("retry_min_wait", 2),
        "retry_max_wait": st.session_state.get("retry_max_wait", 30),
        "run_lock_max_age_hours": st.session_state.get("run_lock_max_age_hours", 12),
        "log_rotation_type": st.session_state.get("log_rotation_type", "time"),
        "log_keep_days": st.session_state.get("log_keep_days", 30),
    }
