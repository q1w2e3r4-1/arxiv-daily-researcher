#!/usr/bin/env python3
"""
ArXiv Daily Researcher - Streamlit Config Panel

Usage:
    streamlit run src/webui/config_panel.py

    Docker:
    docker compose -f docker/docker-compose.yml --profile webui up -d config-panel
"""

import sys
from pathlib import Path

# Add src to path for config_io imports (src/webui/ -> src/ -> project root)
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

import streamlit as st

from utils.config_io import (
    read_env,
    write_env,
    read_config_json,
    write_config_json,
    flatten_config_dict,
    build_config_dict,
    DEFAULT_ENV_PATH,
    DEFAULT_CONFIG_PATH,
)

from webui.styles import CUSTOM_CSS
from webui.tabs import llm, search, keywords, scoring, notifications, advanced, reports
from webui.tabs import run_manager, trend_runner
from webui.i18n import t


# ==================== Page Config ====================

st.set_page_config(
    page_title="ArXiv Researcher - Config",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Initialize language (default: Chinese)
if "lang" not in st.session_state:
    st.session_state["lang"] = "zh"


# ==================== Data Loading ====================


@st.cache_data(ttl=5)
def load_env():
    return read_env()


@st.cache_data(ttl=5)
def load_config():
    raw = read_config_json()
    return flatten_config_dict(raw) if raw else {}


def do_save():
    """保存所有配置到磁盘。"""
    env_values = load_env()
    config_values = load_config()

    # Collect from all tabs
    env_updates = {}
    config_updates = {}

    # API tab (原 LLM tab) -> env only
    env_updates.update(llm.collect(env_values, config_values))

    # Search tab -> config only
    config_updates.update(search.collect(env_values, config_values))

    # Keywords tab -> config only
    config_updates.update(keywords.collect(env_values, config_values))

    # Scoring tab -> config only
    config_updates.update(scoring.collect(env_values, config_values))

    # Notifications tab -> both env and config
    notif_env, notif_cfg = notifications.collect(env_values, config_values)
    env_updates.update(notif_env)
    config_updates.update(notif_cfg)

    # Advanced tab -> config only
    config_updates.update(advanced.collect(env_values, config_values))

    # Trend Runner tab -> config only（趋势分析配置）
    config_updates.update(trend_runner.collect(env_values, config_values))

    # Merge and write env
    merged_env = {**env_values, **env_updates}
    write_env(merged_env)

    # Merge and write config
    merged_config = {**config_values, **config_updates}
    config_dict = build_config_dict(**merged_config)
    write_config_json(config_dict)

    # Clear cache to reload fresh data
    st.cache_data.clear()


# ==================== Sidebar ====================


with st.sidebar:
    st.markdown("### ArXiv Daily Researcher")
    st.caption(t("sidebar_caption"))
    st.divider()

    if st.button(t("save_btn"), type="primary", use_container_width=True, key="save_btn"):
        try:
            do_save()
            st.success(t("save_success"))
        except Exception as e:
            st.error(t("save_failed") + str(e))

    if st.button(t("reload_btn"), use_container_width=True, key="reload_btn"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # File status
    env_exists = DEFAULT_ENV_PATH.exists()
    cfg_exists = DEFAULT_CONFIG_PATH.exists()
    found = t("file_found")
    not_found = t("file_not_found")
    st.markdown(f"`.env`: {found if env_exists else not_found}")
    st.markdown(f"`config.json`: {found if cfg_exists else not_found}")

    st.divider()

    # Language toggle
    lang_label = t("lang_toggle")
    if st.button(lang_label, use_container_width=True, key="lang_btn"):
        st.session_state["lang"] = "en" if st.session_state["lang"] == "zh" else "zh"
        st.rerun()

    st.caption("v3.1 | Powered by Streamlit")


# ==================== Main Content ====================


st.markdown('<p class="main-header">ArXiv Daily Researcher</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="sub-header">{t("sub_header")}</p>',
    unsafe_allow_html=True,
)

# Load data
env_values = load_env()
config_values = load_config()

# Render tabs（9 个 Tab）
tab_labels = [
    t("tab_run_manager"),    # 运行管理
    t("tab_reports"),        # 报告查看
    t("tab_trend_runner"),   # 趋势分析
    t("tab_keywords"),       # 关键词
    t("tab_search"),         # 搜索与数据源
    t("tab_scoring"),        # 评分
    t("tab_notifications"),  # 通知
    t("tab_llm"),            # API
    t("tab_advanced"),       # 高级设置
]
tabs = st.tabs(tab_labels)

with tabs[0]:
    run_manager.render(env_values, config_values)

with tabs[1]:
    reports.render(env_values, config_values)

with tabs[2]:
    trend_runner.render(env_values, config_values)

with tabs[3]:
    keywords.render(env_values, config_values)

with tabs[4]:
    search.render(env_values, config_values)

with tabs[5]:
    scoring.render(env_values, config_values)

with tabs[6]:
    notifications.render(env_values, config_values)

with tabs[7]:
    llm.render(env_values, config_values)

with tabs[8]:
    advanced.render(env_values, config_values)

