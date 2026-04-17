"""API 配置 Tab（含 LLM、MinerU 和其他第三方 API 配置）。"""

import streamlit as st
from webui.i18n import t


# Provider presets
LLM_PROVIDERS = {
    "OpenAI": {"base_url": "https://api.openai.com/v1", "cheap": "gpt-4o-mini", "smart": "gpt-4o"},
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "cheap": "deepseek-chat",
        "smart": "deepseek-chat",
    },
    "Ollama (Local)": {
        "base_url": "http://127.0.0.1:11434/v1",
        "cheap": "qwen2.5:7b",
        "smart": "qwen2.5:14b",
    },
    "Zhipu AI": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "cheap": "glm-4-flash",
        "smart": "glm-4",
    },
    "Custom": {"base_url": "", "cheap": "", "smart": ""},
}


def _detect_provider(base_url: str) -> str:
    """从 base_url 推断 LLM Provider。"""
    for name, info in LLM_PROVIDERS.items():
        if name == "Custom":
            continue
        if info["base_url"] and info["base_url"] in base_url:
            return name
    return "Custom"


def render(env_values: dict, _config_values: dict):
    """渲染 API 配置 Tab。"""

    # ---- CHEAP LLM ----
    st.markdown(f'<p class="section-title">{t("cheap_llm_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("cheap_llm_hint")}</p>', unsafe_allow_html=True)

    current_cheap_base = env_values.get("CHEAP_LLM__BASE_URL", "https://api.openai.com/v1")
    detected_cheap = _detect_provider(current_cheap_base)

    col1, col2 = st.columns([1, 2])
    with col1:
        cheap_provider = st.selectbox(
            t("provider_preset"),
            options=list(LLM_PROVIDERS.keys()),
            index=list(LLM_PROVIDERS.keys()).index(detected_cheap),
            key="cheap_provider",
        )
    with col2:
        preset = LLM_PROVIDERS[cheap_provider]
        cheap_base = st.text_input(
            t("base_url"),
            value=current_cheap_base if cheap_provider == detected_cheap else preset["base_url"],
            key="cheap_base_url",
        )

    col3, col4 = st.columns(2)
    with col3:
        cheap_key = st.text_input(
            t("api_key"),
            value=env_values.get("CHEAP_LLM__API_KEY", ""),
            type="password",
            key="cheap_api_key",
        )
    with col4:
        default_model = env_values.get("CHEAP_LLM__MODEL_NAME", preset["cheap"])
        cheap_model = st.text_input(
            t("model_name"),
            value=default_model,
            key="cheap_model_name",
        )

    cheap_temp = st.slider(
        t("temperature"),
        min_value=0.0,
        max_value=2.0,
        value=float(env_values.get("CHEAP_LLM__TEMPERATURE", "0.3")),
        step=0.1,
        key="cheap_temperature",
    )

    if st.button(t("test_cheap_btn"), key="test_cheap", type="secondary"):
        with st.spinner(t("testing_connection")):
            from utils.config_io import validate_llm_connection

            ok, msg = validate_llm_connection(cheap_key, cheap_base, cheap_model)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.divider()

    # ---- SMART LLM ----
    st.markdown(f'<p class="section-title">{t("smart_llm_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("smart_llm_hint")}</p>', unsafe_allow_html=True)

    current_smart_base = env_values.get("SMART_LLM__BASE_URL", "https://api.openai.com/v1")
    detected_smart = _detect_provider(current_smart_base)

    col5, col6 = st.columns([1, 2])
    with col5:
        smart_provider = st.selectbox(
            t("provider_preset"),
            options=list(LLM_PROVIDERS.keys()),
            index=list(LLM_PROVIDERS.keys()).index(detected_smart),
            key="smart_provider",
        )
    with col6:
        smart_preset = LLM_PROVIDERS[smart_provider]
        smart_base = st.text_input(
            t("base_url"),
            value=(
                current_smart_base if smart_provider == detected_smart else smart_preset["base_url"]
            ),
            key="smart_base_url",
        )

    col7, col8 = st.columns(2)
    with col7:
        smart_key = st.text_input(
            t("api_key"),
            value=env_values.get("SMART_LLM__API_KEY", ""),
            type="password",
            key="smart_api_key",
        )
    with col8:
        default_smart_model = env_values.get("SMART_LLM__MODEL_NAME", smart_preset["smart"])
        smart_model = st.text_input(
            t("model_name"),
            value=default_smart_model,
            key="smart_model_name",
        )

    smart_temp = st.slider(
        t("temperature"),
        min_value=0.0,
        max_value=2.0,
        value=float(env_values.get("SMART_LLM__TEMPERATURE", "0.3")),
        step=0.1,
        key="smart_temperature",
    )

    if st.button(t("test_smart_btn"), key="test_smart", type="secondary"):
        with st.spinner(t("testing_connection")):
            from utils.config_io import validate_llm_connection

            ok, msg = validate_llm_connection(smart_key, smart_base, smart_model)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    # ---- MinerU API ----
    st.divider()
    st.markdown(f'<p class="section-title">{t("mineru_section_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("mineru_section_hint")}</p>', unsafe_allow_html=True)

    mineru_key = st.text_input(
        t("mineru_api_key_label"),
        value=env_values.get("MINERU_API_KEY", ""),
        type="password",
        key="mineru_key",
        help=t("mineru_key_help"),
    )

    col_m1, col_m2 = st.columns([1, 3])
    with col_m1:
        test_mineru_btn = st.button(
            t("test_mineru_btn"), key="test_mineru", type="secondary", use_container_width=True
        )
    with col_m2:
        st.caption(t("mineru_expire_note"))

    if test_mineru_btn:
        with st.spinner(t("testing_mineru")):
            from utils.config_io import validate_mineru_connection

            ok, msg = validate_mineru_connection(mineru_key)
        if ok:
            st.success(msg)
        else:
            st.warning(msg)

    # 展示当前 Token 过期状态提醒（仅当有 key 时）
    current_mineru_key = env_values.get("MINERU_API_KEY", "")
    if current_mineru_key and not mineru_key:
        # 已保存 key 但当前输入框为空（密码框默认不显示值）
        pass

    st.divider()

    # ---- 其他第三方 API Keys ----
    st.markdown(
        f'<p class="section-title">{t("third_party_keys_title")}</p>', unsafe_allow_html=True
    )
    st.markdown(f'<p class="hint-text">{t("third_party_keys_hint")}</p>', unsafe_allow_html=True)

    col9, col10 = st.columns(2)
    with col9:
        st.text_input(
            t("openalex_email_label"),
            value=env_values.get("OPENALEX_EMAIL", ""),
            key="openalex_email",
        )
        st.text_input(
            t("s2_api_key_label"),
            value=env_values.get("SEMANTIC_SCHOLAR_API_KEY", ""),
            type="password",
            key="semantic_scholar_key",
        )
    with col10:
        st.text_input(
            t("openalex_api_key_label"),
            value=env_values.get("OPENALEX_API_KEY", ""),
            type="password",
            key="openalex_key",
        )


def collect(env_values: dict, _config_values: dict) -> dict:
    """从 session_state 收集当前值，返回 env 更新字典。"""
    return {
        "CHEAP_LLM__API_KEY": st.session_state.get("cheap_api_key", ""),
        "CHEAP_LLM__BASE_URL": st.session_state.get("cheap_base_url", ""),
        "CHEAP_LLM__MODEL_NAME": st.session_state.get("cheap_model_name", ""),
        "CHEAP_LLM__TEMPERATURE": str(st.session_state.get("cheap_temperature", 0.3)),
        "SMART_LLM__API_KEY": st.session_state.get("smart_api_key", ""),
        "SMART_LLM__BASE_URL": st.session_state.get("smart_base_url", ""),
        "SMART_LLM__MODEL_NAME": st.session_state.get("smart_model_name", ""),
        "SMART_LLM__TEMPERATURE": str(st.session_state.get("smart_temperature", 0.3)),
        "OPENALEX_EMAIL": st.session_state.get("openalex_email", ""),
        "OPENALEX_API_KEY": st.session_state.get("openalex_key", ""),
        "SEMANTIC_SCHOLAR_API_KEY": st.session_state.get("semantic_scholar_key", ""),
        "MINERU_API_KEY": st.session_state.get("mineru_key", ""),
    }
