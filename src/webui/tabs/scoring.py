"""Scoring Configuration tab for the Streamlit config panel."""

import streamlit as st
from webui.i18n import t


DEFAULT_COMMITTEE_MODELS = ["minimax-m2.7", "qwen3.5-27b", "deepseek-v3.2"]


def render(_env_values: dict, config_values: dict):
    """Render the Scoring configuration tab."""

    flat = config_values

    st.markdown(f'<p class="section-title">🧮 {t("scoring_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("scoring_hint")}</p>', unsafe_allow_html=True)

    method_options = ["keyword_weighted", "mlsys_multi_model"]
    method_labels = {
        "keyword_weighted": t("scoring_method_keyword"),
        "mlsys_multi_model": t("scoring_method_committee"),
    }
    current_method = flat.get("scoring_method", "keyword_weighted")
    current_index = method_options.index(current_method) if current_method in method_options else 0

    selected_method = st.radio(
        t("scoring_method_label"),
        options=method_options,
        index=current_index,
        format_func=lambda value: method_labels[value],
        key="scoring_method",
        horizontal=True,
    )

    if selected_method == "keyword_weighted":
        st.markdown(f'<p class="section-title">📐 {t("keyword_formula_title")}</p>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.number_input(
                t("base_score_label"),
                min_value=0.0,
                max_value=100.0,
                value=float(flat.get("passing_score_base", 5.0)),
                step=0.5,
                key="passing_score_base",
            )
        with col2:
            st.number_input(
                t("weight_coeff_label"),
                min_value=0.0,
                max_value=20.0,
                value=float(flat.get("passing_score_weight_coefficient", 3.0)),
                step=0.5,
                key="passing_score_weight_coefficient",
            )
        with col3:
            st.number_input(
                t("max_score_per_kw_label"),
                min_value=1,
                max_value=100,
                value=flat.get("max_score_per_keyword", 10),
                key="max_score_per_keyword",
            )

        keywords = flat.get("primary_keywords", [])
        weight = flat.get("primary_keyword_weight", 1.0)
        base = st.session_state.get("passing_score_base", flat.get("passing_score_base", 5.0))
        coeff = st.session_state.get(
            "passing_score_weight_coefficient", flat.get("passing_score_weight_coefficient", 3.0)
        )
        total_weight = len(keywords) * weight
        passing = base + coeff * total_weight

        lang = st.session_state.get("lang", "zh")
        if lang == "zh":
            info_msg = (
                f"共 {len(keywords)} 个关键词，权重 {weight}："
                f"通过分数 = {base} + {coeff} × {total_weight:.1f} = **{passing:.1f}**"
            )
        else:
            info_msg = (
                f"With {len(keywords)} keyword(s) at weight {weight}: "
                f"Passing Score = {base} + {coeff} x {total_weight:.1f} = **{passing:.1f}**"
            )
        st.info(info_msg)

        st.divider()

        st.markdown(
            f'<p class="section-title">👤 {t("author_bonus_title")}</p>', unsafe_allow_html=True
        )
        st.markdown(f'<p class="hint-text">{t("author_bonus_hint")}</p>', unsafe_allow_html=True)

        st.toggle(
            t("enable_author_bonus"),
            value=flat.get("enable_author_bonus", False),
            key="enable_author_bonus",
        )

        if st.session_state.get("enable_author_bonus", False):
            col4, col5 = st.columns([3, 1])
            with col4:
                current_authors = flat.get("expert_authors", [])
                st.text_area(
                    t("expert_authors_label"),
                    value="\n".join(current_authors),
                    height=100,
                    key="expert_authors_text",
                    help=t("expert_authors_help"),
                )
            with col5:
                st.number_input(
                    t("bonus_points_label"),
                    min_value=0.0,
                    max_value=50.0,
                    value=float(flat.get("author_bonus_points", 5.0)),
                    step=0.5,
                    key="author_bonus_points",
                )
    else:
        st.markdown(f'<p class="section-title">🤝 {t("committee_title")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="hint-text">{t("committee_hint")}</p>', unsafe_allow_html=True)

        committee_models = flat.get("mlsys_committee_models", DEFAULT_COMMITTEE_MODELS)
        st.text_area(
            t("committee_models_label"),
            value="\n".join(committee_models),
            height=120,
            key="mlsys_committee_models_text",
            help=t("committee_models_help"),
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.number_input(
                t("committee_pass_score_label"),
                min_value=0.0,
                max_value=20.0,
                value=float(flat.get("mlsys_passing_score", 6.0)),
                step=0.5,
                key="mlsys_passing_score",
            )
        with col2:
            st.number_input(
                t("committee_fallback_score_label"),
                min_value=0.0,
                max_value=20.0,
                value=float(flat.get("mlsys_fallback_score", 5.0)),
                step=0.5,
                key="mlsys_fallback_score",
            )
        with col3:
            st.number_input(
                t("committee_breaker_label"),
                min_value=1,
                max_value=20,
                value=int(flat.get("mlsys_circuit_breaker_threshold", 3)),
                step=1,
                key="mlsys_circuit_breaker_threshold",
            )

        st.toggle(
            t("committee_export_artifacts"),
            value=flat.get("mlsys_export_artifacts", True),
            key="mlsys_export_artifacts",
        )

        st.markdown(
            f'<p class="section-title">🧠 {t("committee_smart_review_title")}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<p class="hint-text">{t("committee_smart_review_help")}</p>', unsafe_allow_html=True)
        st.toggle(
            t("committee_smart_review_enabled"),
            value=flat.get("mlsys_smart_review_enabled", True),
            key="mlsys_smart_review_enabled",
        )
        col4, col5 = st.columns(2)
        with col4:
            st.number_input(
                t("committee_smart_review_min"),
                min_value=0.0,
                max_value=20.0,
                value=float(flat.get("mlsys_smart_review_min_score", 5.0)),
                step=0.5,
                key="mlsys_smart_review_min_score",
            )
        with col5:
            st.number_input(
                t("committee_smart_review_max"),
                min_value=0.0,
                max_value=20.0,
                value=float(flat.get("mlsys_smart_review_max_score", 7.0)),
                step=0.5,
                key="mlsys_smart_review_max_score",
            )

        pass_score = st.session_state.get("mlsys_passing_score", flat.get("mlsys_passing_score", 6.0))
        fallback_score = st.session_state.get(
            "mlsys_fallback_score", flat.get("mlsys_fallback_score", 5.0)
        )
        breaker = st.session_state.get(
            "mlsys_circuit_breaker_threshold", flat.get("mlsys_circuit_breaker_threshold", 3)
        )
        smart_review_enabled = st.session_state.get(
            "mlsys_smart_review_enabled", flat.get("mlsys_smart_review_enabled", True)
        )
        smart_review_min = st.session_state.get(
            "mlsys_smart_review_min_score", flat.get("mlsys_smart_review_min_score", 5.0)
        )
        smart_review_max = st.session_state.get(
            "mlsys_smart_review_max_score", flat.get("mlsys_smart_review_max_score", 7.0)
        )
        review_text = (
            f"SMART_LLM review on averages in **[{smart_review_min:.1f}, {smart_review_max:.1f}]**"
            if smart_review_enabled
            else "SMART_LLM review disabled"
        )
        st.info(
            f"Staged rule: first average the cheap first-pass models; then {review_text}; "
            f"final pass threshold = **{pass_score:.1f}**, fallback score = **{fallback_score:.1f}**, "
            f"circuit breaker = **{breaker}**."
        )


def collect(_env_values: dict, _config_values: dict) -> dict:
    """Collect current values from session state. Returns config updates."""
    result = {
        "scoring_method": st.session_state.get("scoring_method", "keyword_weighted"),
        "passing_score_base": st.session_state.get("passing_score_base", 5.0),
        "passing_score_weight_coefficient": st.session_state.get(
            "passing_score_weight_coefficient", 3.0
        ),
        "max_score_per_keyword": st.session_state.get("max_score_per_keyword", 10),
        "enable_author_bonus": st.session_state.get("enable_author_bonus", False),
        "mlsys_passing_score": st.session_state.get("mlsys_passing_score", 6.0),
        "mlsys_fallback_score": st.session_state.get("mlsys_fallback_score", 5.0),
        "mlsys_circuit_breaker_threshold": st.session_state.get(
            "mlsys_circuit_breaker_threshold", 3
        ),
        "mlsys_export_artifacts": st.session_state.get("mlsys_export_artifacts", True),
        "mlsys_smart_review_enabled": st.session_state.get("mlsys_smart_review_enabled", True),
        "mlsys_smart_review_min_score": st.session_state.get("mlsys_smart_review_min_score", 5.0),
        "mlsys_smart_review_max_score": st.session_state.get("mlsys_smart_review_max_score", 7.0),
    }

    models_text = st.session_state.get("mlsys_committee_models_text", "")
    models = [line.strip() for line in models_text.split("\n") if line.strip()]
    result["mlsys_committee_models"] = models or DEFAULT_COMMITTEE_MODELS

    if result["enable_author_bonus"]:
        authors_text = st.session_state.get("expert_authors_text", "")
        result["expert_authors"] = [a.strip() for a in authors_text.split("\n") if a.strip()]
        result["author_bonus_points"] = st.session_state.get("author_bonus_points", 5.0)
    else:
        result["expert_authors"] = []
        result["author_bonus_points"] = _config_values.get("author_bonus_points", 5.0)

    return result
