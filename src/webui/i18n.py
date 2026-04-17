"""
Internationalization (i18n) support for the Streamlit config panel.

Provides a t() function that returns the translated string based on the
current language stored in st.session_state["lang"] (default: "zh").
"""

import streamlit as st

# ─── Translation dictionary ────────────────────────────────────────────────
_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── config_panel.py ──────────────────────────────────────────────────
    "sidebar_caption": {
        "zh": "配置面板",
        "en": "Configuration Panel",
    },
    "save_btn": {
        "zh": "保存所有更改",
        "en": "Save All Changes",
    },
    "reload_btn": {
        "zh": "从磁盘重新加载",
        "en": "Reload from Disk",
    },
    "save_success": {
        "zh": "配置已保存！",
        "en": "Configuration saved!",
    },
    "save_failed": {
        "zh": "保存失败: ",
        "en": "Save failed: ",
    },
    "file_found": {
        "zh": "已找到",
        "en": "Found",
    },
    "file_not_found": {
        "zh": "未找到",
        "en": "Not found",
    },
    "sub_header": {
        "zh": "配置面板 — 编辑 .env 和 configs/config.json",
        "en": "Configuration Panel — Edit .env and configs/config.json",
    },
    "lang_toggle": {
        "zh": "English",
        "en": "中文",
    },
    # Tab labels
    "tab_llm": {"zh": "API", "en": "API"},
    "tab_search": {"zh": "搜索与数据源", "en": "Search & Sources"},
    "tab_keywords": {"zh": "关键词", "en": "Keywords"},
    "tab_scoring": {"zh": "评分", "en": "Scoring"},
    "tab_notifications": {"zh": "通知", "en": "Notifications"},
    "tab_advanced": {"zh": "高级设置", "en": "Advanced"},
    "tab_reports": {"zh": "报告查看", "en": "Reports"},
    "tab_run_manager": {"zh": "运行管理", "en": "Run Manager"},
    "tab_trend_runner": {"zh": "趋势分析", "en": "Trend Analysis"},
    # ── llm.py ───────────────────────────────────────────────────────────
    "cheap_llm_title": {
        "zh": "低成本 LLM (CHEAP_LLM)",
        "en": "Low-Cost LLM (CHEAP_LLM)",
    },
    "cheap_llm_hint": {
        "zh": "用于快速评分和关键词生成，选择速度快、成本低的模型。",
        "en": "Used for quick scoring and keyword generation. Choose a fast, cheap model.",
    },
    "provider_preset": {"zh": "服务商预设", "en": "Provider Preset"},
    "base_url": {"zh": "Base URL", "en": "Base URL"},
    "api_key": {"zh": "API Key", "en": "API Key"},
    "model_name": {"zh": "模型名称", "en": "Model Name"},
    "temperature": {"zh": "Temperature", "en": "Temperature"},
    "test_cheap_btn": {
        "zh": "测试 CHEAP_LLM 连接",
        "en": "Test CHEAP_LLM Connection",
    },
    "test_smart_btn": {
        "zh": "测试 SMART_LLM 连接",
        "en": "Test SMART_LLM Connection",
    },
    "testing_connection": {"zh": "测试连接中...", "en": "Testing connection..."},
    "smart_llm_title": {
        "zh": "高性能 LLM (SMART_LLM)",
        "en": "High-Performance LLM (SMART_LLM)",
    },
    "smart_llm_hint": {
        "zh": "用于深度分析和内容理解，选择能力强的模型。",
        "en": "Used for deep analysis and content understanding. Choose a capable model.",
    },
    "third_party_keys_title": {
        "zh": "第三方 API 密钥",
        "en": "Third-Party API Keys",
    },
    "third_party_keys_hint": {
        "zh": "可选的 API 密钥，用于增强功能。",
        "en": "Optional API keys for enhanced features.",
    },
    "openalex_email_label": {
        "zh": "OpenAlex Email（提升速率限制）",
        "en": "OpenAlex Email (improves rate limit)",
    },
    "s2_api_key_label": {
        "zh": "Semantic Scholar API Key",
        "en": "Semantic Scholar API Key",
    },
    "openalex_api_key_label": {
        "zh": "OpenAlex API Key",
        "en": "OpenAlex API Key",
    },
    "mineru_api_key_label": {
        "zh": "MinerU API Key",
        "en": "MinerU API Key",
    },
    "mineru_section_title": {
        "zh": "MinerU PDF 解析 API",
        "en": "MinerU PDF Parsing API",
    },
    "mineru_section_hint": {
        "zh": "MinerU 提供高质量云端 PDF 解析，Token 每 3 个月过期。点击「测试」可查看颟度余量和过期时间。",
        "en": "MinerU provides high-quality cloud PDF parsing. Token expires every 3 months. Click Test to check quota and expiry.",
    },
    "mineru_key_help": {
        "zh": "登录 mineru.net 获取 API Token",
        "en": "Get your API token from mineru.net",
    },
    "test_mineru_btn": {"zh": "测试 MinerU 连接", "en": "Test MinerU Connection"},
    "testing_mineru": {"zh": "连接 MinerU 中...", "en": "Connecting to MinerU..."},
    "mineru_expire_note": {
        "zh": "点击测试可查看 Token 过期日期和剩余颟度",
        "en": "Click Test to check token expiry and remaining quota",
    },
    # ── reports.py 导航按钞 ──
    "report_prev_day": {"zh": "← 前一天", "en": "← Prev Day"},
    "report_next_day": {"zh": "后一天 →", "en": "Next Day →"},
    "report_show_non_arxiv": {"zh": "显示非 ArXiv 来源", "en": "Show non-ArXiv sources"},
    "report_no_prev": {"zh": "已是最早的报告", "en": "No earlier reports"},
    "report_no_next": {"zh": "已是最新的报告", "en": "No newer reports"},
    # ── run_manager.py ──
    "run_manager_title": {"zh": "运行管理", "en": "Run Manager"},
    "run_now_section_title": {"zh": "立即运行每日研究", "en": "Run Daily Research Now"},
    "run_now_btn": {"zh": "立即运行", "en": "Run Now"},
    "run_now_hint": {
        "zh": "立即执行一次每日研究流水线（包含抓取论文、评分、分析和发送通知）。",
        "en": "Immediately run the daily research pipeline (fetch, score, analyze, notify).",
    },
    "stop_all_btn": {"zh": "停止所有进程", "en": "Stop All Processes"},
    "stop_all_hint": {
        "zh": "向所有正在运行的每日研究和趋势分析进程发送停止信号。",
        "en": "Send stop signal to all running daily research and trend analysis processes.",
    },
    "run_log_title": {"zh": "运行日志", "en": "Run Logs"},
    "no_logs_found": {"zh": "暂未找到日志文件。", "en": "No log files found."},
    "pid_killed": {"zh": "已向进程 {pid} 发送停止信号", "en": "Sent stop signal to process {pid}"},
    "no_running_process": {
        "zh": "未检测到正在运行的进程。",
        "en": "No running processes detected.",
    },
    "process_started": {
        "zh": "进程已启动，日志将实时生成。",
        "en": "Process started. Logs will appear shortly.",
    },
    # run_manager 状态标签
    "rm_status_title": {"zh": "当前运行状态", "en": "Current Run Status"},
    "rm_no_running_tasks": {
        "zh": "当前无正在运行的任务（无锁/PID 文件）。",
        "en": "No running tasks (no lock/PID files).",
    },
    "rm_status_running": {"zh": "运行中", "en": "Running"},
    "rm_status_stopped": {"zh": "已停止（文件未清除）", "en": "Stopped (file not cleaned)"},
    "rm_no_pid": {"zh": "无 PID", "en": "No PID"},
    "rm_started_at": {"zh": "启动于", "en": "Started at"},
    "rm_process_running_label": {
        "zh": "面板触发的进程正在运行",
        "en": "Panel-triggered process is running",
    },
    "rm_no_panel_process": {
        "zh": "当前无面板触发的进程运行",
        "en": "No panel-triggered process running",
    },
    # run_manager Docker 模式
    "rm_docker_exec_hint": {
        "zh": "Docker 模式：通过 docker exec 在容器 {container} 中触发每日研究",
        "en": "Docker mode: triggers daily research via docker exec in container {container}",
    },
    "rm_docker_no_sock_warning": {
        "zh": (
            "⚠️ Docker 模式（无 Docker Socket）：无法直接启动任务。\n\n"
            "请在宿主机终端运行：\n"
            "`docker exec {container} python main.py --mode daily_research`"
        ),
        "en": (
            "⚠️ Docker mode (no Docker socket): cannot start tasks directly.\n\n"
            "Run on host terminal:\n"
            "`docker exec {container} python main.py --mode daily_research`"
        ),
    },
    "rm_docker_log_hint": {
        "zh": "（Docker 模式：确认 `logs/` 目录已通过卷挂载共享到此容器）",
        "en": "(Docker mode: ensure `logs/` is mounted into this container via a volume)",
    },
    # run_manager 日志选择器
    "rm_select_log_label": {"zh": "选择日志文件", "en": "Select log file"},
    "rm_select_log_help": {
        "zh": "按分类显示所有日志文件，括号内为最后修改时间",
        "en": "All log files grouped by type. Bracket shows last modified time.",
    },
    "rm_log_group_daily": {"zh": "每日研究日志", "en": "Daily Research"},
    "rm_log_group_trend": {"zh": "趋势分析日志", "en": "Trend Analysis"},
    "rm_log_group_other": {"zh": "其他日志", "en": "Other"},
    "rm_open_log_btn": {"zh": "打开", "en": "Open"},
    "rm_refresh_log_btn": {"zh": "刷新", "en": "Refresh"},
    "rm_close_log_btn": {"zh": "关闭", "en": "Close"},
    # ── trend_runner.py ──
    "trend_runner_title": {"zh": "趋势分析", "en": "Trend Analysis"},
    "trend_keywords_label": {"zh": "搜索关键词", "en": "Search Keywords"},
    "trend_keywords_help": {
        "zh": '多个关键词用空格分隔，引号包裹短语，如: quantum error correction "surface code"',
        "en": 'Multiple keywords separated by spaces. Quote phrases, e.g.: quantum error correction "surface code"',
    },
    "trend_date_from": {"zh": "起始日期", "en": "Date From"},
    "trend_date_to": {"zh": "截止日期", "en": "Date To"},
    "trend_categories_label": {
        "zh": "ArXiv 分类过滤（可选）",
        "en": "ArXiv Categories Filter (optional)",
    },
    "trend_categories_help": {
        "zh": "多个分类用空格分隔，如: quant-ph cs.AI",
        "en": "Multiple categories separated by spaces, e.g.: quant-ph cs.AI",
    },
    "trend_run_btn": {"zh": "开始趋势分析", "en": "Start Trend Analysis"},
    "trend_config_title": {"zh": "趋势分析配置", "en": "Trend Analysis Configuration"},
    "trend_sort_label": {"zh": "时间排序", "en": "Time Sort Order"},
    "trend_generate_tldr_label": {"zh": "生成 TLDR", "en": "Generate TLDR"},
    "trend_tldr_batch_label": {"zh": "TLDR 批次并发数", "en": "TLDR Batch Size"},
    "trend_skills_label": {"zh": "启用的分析技能", "en": "Enabled Analysis Skills"},
    "trend_output_formats_label": {"zh": "输出格式", "en": "Output Formats"},
    # ── search.py ────────────────────────────────────────────────────────
    "search_settings_title": {"zh": "搜索设置", "en": "Search Settings"},
    "search_settings_hint": {
        "zh": "控制每次抓取的论文数量和时间范围。",
        "en": "Control how many papers to fetch and the time range.",
    },
    "search_days_label": {"zh": "搜索最近 N 天", "en": "Search recent N days"},
    "search_days_help": {
        "zh": "推荐：1（每日）、7（每周）、30（每月）",
        "en": "Recommended: 1 (daily), 7 (weekly), 30 (monthly)",
    },
    "max_results_label": {"zh": "每个数据源最大结果数", "en": "Max results per source"},
    "max_results_help": {"zh": "推荐：50-200", "en": "Recommended: 50-200"},
    "data_sources_title": {"zh": "数据源", "en": "Data Sources"},
    "data_sources_hint": {
        "zh": "选择要监控的论文来源。",
        "en": "Select which paper sources to monitor.",
    },
    "reports_by_source_toggle": {
        "zh": "按数据源分类整理报告",
        "en": "Organize reports by source",
    },
    "reports_by_source_help": {
        "zh": "为每个数据源创建独立报告目录",
        "en": "Create separate report directories for each data source",
    },
    "arxiv_fetch_timeout_label": {
        "zh": "ArXiv 抓取超时（秒）",
        "en": "ArXiv fetch timeout (seconds)",
    },
    "arxiv_fetch_timeout_help": {
        "zh": "单次 ArXiv 抓取硬超时，超时后自动重试，避免任务长时间卡住",
        "en": "Hard timeout for one ArXiv fetch. Retries on timeout to avoid stuck runs.",
    },
    "arxiv_domains_title": {"zh": "ArXiv 目标分类", "en": "ArXiv Target Domains"},
    "arxiv_domains_hint": {
        "zh": "ArXiv 分类代码，详见 https://arxiv.org/category_taxonomy",
        "en": "ArXiv category codes. See: https://arxiv.org/category_taxonomy",
    },
    "select_arxiv_cats": {
        "zh": "选择 ArXiv 分类",
        "en": "Select ArXiv categories",
    },
    "custom_domains_label": {
        "zh": "其他自定义分类（逗号分隔）",
        "en": "Additional custom domains (comma-separated)",
    },
    "custom_domains_help": {
        "zh": "输入不在列表中的 ArXiv 分类代码",
        "en": "Enter ArXiv category codes not in the list above",
    },
    # ── keywords.py ──────────────────────────────────────────────────────
    "primary_keywords_title": {"zh": "主要关键词", "en": "Primary Keywords"},
    "primary_keywords_hint": {
        "zh": "用于论文相关性评分的关键词，权重越高越重要。",
        "en": "Keywords used for paper relevance scoring. Higher weight = more importance.",
    },
    "keywords_textarea_label": {
        "zh": "主要关键词（每行一个）",
        "en": "Primary Keywords (one per line)",
    },
    "keywords_textarea_help": {
        "zh": "每行输入一个关键词，用于匹配论文标题和摘要。",
        "en": "Enter one keyword per line. These are matched against paper titles and abstracts.",
    },
    "keyword_weight_slider": {
        "zh": "主要关键词权重",
        "en": "Primary Keyword Weight",
    },
    "ref_extract_title": {
        "zh": "参考文献 PDF 关键词提取",
        "en": "Reference PDF Extraction",
    },
    "ref_extract_hint": {
        "zh": "自动从 data/reference_pdfs/ 中的参考 PDF 提取关键词。",
        "en": "Automatically extract keywords from reference PDFs in data/reference_pdfs/",
    },
    "enable_ref_extract": {
        "zh": "启用参考文献关键词提取",
        "en": "Enable reference keyword extraction",
    },
    "ref_extract_expander": {
        "zh": "参考文献提取设置",
        "en": "Reference Extraction Settings",
    },
    "max_extracted_kws": {
        "zh": "最大提取关键词数",
        "en": "Max extracted keywords",
    },
    "similarity_threshold_label": {
        "zh": "相似度阈值",
        "en": "Similarity threshold",
    },
    "similarity_threshold_help": {
        "zh": "相似度高于此阈值的关键词将被去重",
        "en": "Keywords above this similarity are de-duplicated",
    },
    "weight_distribution": {
        "zh": "**权重分布**",
        "en": "**Weight Distribution**",
    },
    "high_importance": {"zh": "*高重要性*", "en": "*High Importance*"},
    "medium_importance": {"zh": "*中重要性*", "en": "*Medium Importance*"},
    "low_importance": {"zh": "*低重要性*", "en": "*Low Importance*"},
    "weight_label": {"zh": "权重", "en": "Weight"},
    "count_label": {"zh": "数量", "en": "Count"},
    "research_context_title": {"zh": "研究背景", "en": "Research Context"},
    "research_context_hint": {
        "zh": "描述你的研究领域，帮助 LLM 更好地理解相关性。",
        "en": "Describe your research area to help the LLM better understand relevance.",
    },
    "research_context_label": {"zh": "研究背景", "en": "Research Context"},
    "research_context_placeholder": {
        "zh": "例如：我研究量子纠错和拓扑量子计算...",
        "en": "e.g., I study quantum error correction and topological quantum computing...",
    },
    # ── scoring.py ───────────────────────────────────────────────────────
    "scoring_title": {"zh": "通过分数公式", "en": "Passing Score Formula"},
    "scoring_hint": {
        "zh": "通过分数 = 基础分 + 权重系数 × 关键词权重总和",
        "en": "Passing Score = Base Score + Weight Coefficient x Sum(Keyword Weights)",
    },
    "base_score_label": {"zh": "基础分", "en": "Base Score"},
    "weight_coeff_label": {"zh": "权重系数", "en": "Weight Coefficient"},
    "max_score_per_kw_label": {
        "zh": "每个关键词最高得分",
        "en": "Max Score Per Keyword",
    },
    "author_bonus_title": {"zh": "作者加分", "en": "Author Bonus"},
    "author_bonus_hint": {
        "zh": "给指定作者的论文额外加分。",
        "en": "Give extra points to papers by specific authors.",
    },
    "enable_author_bonus": {
        "zh": "启用作者加分",
        "en": "Enable author bonus",
    },
    "expert_authors_label": {
        "zh": "专家作者（每行一个）",
        "en": "Expert Authors (one per line)",
    },
    "expert_authors_help": {
        "zh": "包含这些作者的论文将获得额外分数",
        "en": "Papers with these authors receive bonus points",
    },
    "bonus_points_label": {"zh": "加分分值", "en": "Bonus Points"},
    "report_settings_title": {"zh": "报告设置", "en": "Report Settings"},
    "include_all_in_report": {
        "zh": "报告中包含所有论文（不仅是通过的）",
        "en": "Include all papers in report (not just passing)",
    },
    "include_all_help": {
        "zh": "关闭后，报告中只包含高于通过分数的论文",
        "en": "If disabled, only papers above the passing score are included",
    },
    # ── notifications.py ─────────────────────────────────────────────────
    "notif_settings_title": {"zh": "通知设置", "en": "Notification Settings"},
    "notif_settings_hint": {
        "zh": "运行完成时发送通知，在下方配置各通知渠道。",
        "en": "Send notifications when runs complete. Configure channels below.",
    },
    "enable_notifications": {
        "zh": "启用通知",
        "en": "Enable notifications",
    },
    "notify_success": {"zh": "成功时通知", "en": "Notify on success"},
    "notify_failure": {"zh": "失败时通知", "en": "Notify on failure"},
    "top_n_label": {"zh": "通知中展示 Top-N 篇论文", "en": "Top-N papers in notification"},
    "attach_reports": {
        "zh": "邮件附带报告文件",
        "en": "Attach report files to email",
    },
    "email_expander": {"zh": "邮件 (SMTP)", "en": "Email (SMTP)"},
    "enable_email": {"zh": "启用邮件", "en": "Enable Email"},
    "smtp_host_label": {"zh": "SMTP 服务器", "en": "SMTP Host"},
    "smtp_port_label": {"zh": "SMTP 端口", "en": "SMTP Port"},
    "use_tls_label": {"zh": "使用 TLS", "en": "Use TLS"},
    "smtp_user_label": {"zh": "SMTP 用户名", "en": "SMTP User"},
    "smtp_password_label": {"zh": "SMTP 密码", "en": "SMTP Password"},
    "from_address_label": {"zh": "发件人地址", "en": "From Address"},
    "to_addresses_label": {
        "zh": "收件人地址（逗号分隔）",
        "en": "To Addresses (comma-separated)",
    },
    "test_email_btn": {"zh": "测试邮件连接", "en": "Test Email Connection"},
    "testing_smtp": {"zh": "测试 SMTP 中...", "en": "Testing SMTP..."},
    "wechat_expander": {"zh": "企业微信", "en": "WeChat Work"},
    "enable_wechat": {"zh": "启用企业微信", "en": "Enable WeChat Work"},
    "webhook_url_label": {"zh": "Webhook URL", "en": "Webhook URL"},
    "dingtalk_expander": {"zh": "钉钉", "en": "DingTalk"},
    "enable_dingtalk": {"zh": "启用钉钉", "en": "Enable DingTalk"},
    "secret_optional_label": {"zh": "签名密钥（可选）", "en": "Secret (optional)"},
    "telegram_expander": {"zh": "Telegram", "en": "Telegram"},
    "enable_telegram": {"zh": "启用 Telegram", "en": "Enable Telegram"},
    "bot_token_label": {"zh": "Bot Token", "en": "Bot Token"},
    "chat_id_label": {"zh": "Chat ID", "en": "Chat ID"},
    "slack_expander": {"zh": "Slack", "en": "Slack"},
    "enable_slack": {"zh": "启用 Slack", "en": "Enable Slack"},
    "generic_webhook_expander": {
        "zh": "通用 Webhook",
        "en": "Generic Webhook",
    },
    "enable_generic_webhook": {
        "zh": "启用通用 Webhook",
        "en": "Enable Generic Webhook",
    },
    # ── advanced.py ──────────────────────────────────────────────────────
    "pdf_parser_title": {"zh": "PDF 解析器", "en": "PDF Parser"},
    "pdf_parser_hint": {
        "zh": "选择解析研究论文 PDF 的方式。",
        "en": "Choose how to parse research paper PDFs.",
    },
    "parser_mode_label": {"zh": "解析器模式", "en": "Parser Mode"},
    "parser_mode_help": {
        "zh": "mineru：云端 API（质量更高）| pymupdf：本地（无需网络）",
        "en": "mineru: cloud API (higher quality) | pymupdf: local (no network)",
    },
    "mineru_version_label": {
        "zh": "MinerU 模型版本",
        "en": "MinerU Model Version",
    },
    "mineru_version_help": {
        "zh": "pipeline：速度快 | vlm：更精准（消耗更多配额）",
        "en": "pipeline: fast | vlm: more accurate (uses more quota)",
    },
    "concurrency_title": {"zh": "并发设置", "en": "Concurrency"},
    "concurrency_hint": {
        "zh": "LLM 评分的并行处理，注意 API 速率限制。",
        "en": "Parallel processing for LLM scoring. Watch for API rate limits.",
    },
    "enable_concurrency": {
        "zh": "启用并发处理",
        "en": "Enable concurrent processing",
    },
    "worker_threads_label": {"zh": "工作线程数", "en": "Worker threads"},
    "worker_threads_help": {
        "zh": "推荐：3-5，过高可能触发速率限制。",
        "en": "Recommended: 3-5. Higher values may trigger rate limits.",
    },
    "advanced_reports_title": {"zh": "报告", "en": "Reports"},
    "html_reports_label": {"zh": "HTML 报告", "en": "HTML reports"},
    "token_tracking_label": {"zh": "Token 用量追踪", "en": "Token tracking"},
    "auto_update_label": {"zh": "自动更新检查", "en": "Auto-update check"},
    "kw_tracker_title": {
        "zh": "关键词趋势追踪",
        "en": "Keyword Trend Tracking",
    },
    "enable_kw_tracker": {
        "zh": "启用关键词追踪",
        "en": "Enable keyword tracking",
    },
    "kw_tracker_expander": {
        "zh": "关键词追踪设置",
        "en": "Keyword Tracker Settings",
    },
    "ai_normalization_label": {
        "zh": "AI 归一化",
        "en": "AI normalization",
    },
    "normalization_batch_label": {
        "zh": "归一化批次大小",
        "en": "Normalization batch size",
    },
    "trend_view_days_label": {
        "zh": "默认趋势视图天数",
        "en": "Default trend view (days)",
    },
    "bar_chart_top_n_label": {
        "zh": "柱状图 Top-N",
        "en": "Bar chart top-N",
    },
    "trend_chart_top_n_label": {
        "zh": "趋势图 Top-N",
        "en": "Trend chart top-N",
    },
    "enable_trend_reports_label": {
        "zh": "启用趋势报告",
        "en": "Enable trend reports",
    },
    "report_frequency_label": {
        "zh": "报告频率",
        "en": "Report frequency",
    },
    "retry_title": {"zh": "重试与日志", "en": "Retry & Logging"},
    "max_retries_label": {"zh": "最大重试次数", "en": "Max retry attempts"},
    "min_wait_label": {"zh": "最短等待（秒）", "en": "Min wait (seconds)"},
    "max_wait_label": {"zh": "最长等待（秒）", "en": "Max wait (seconds)"},
    "run_lock_max_age_label": {
        "zh": "运行锁超龄回收阈值（小时）",
        "en": "Run-lock stale recovery threshold (hours)",
    },
    "run_lock_max_age_help": {
        "zh": "同一任务持续运行超过该时长将尝试终止并回收锁",
        "en": (
            "If a task runs longer than this, the lock recovery will try to "
            "terminate and reclaim."
        ),
    },
    "log_rotation_label": {"zh": "日志轮转方式", "en": "Log rotation"},
    "log_retention_label": {"zh": "日志保留天数", "en": "Log retention (days)"},
    "trend_research_title": {
        "zh": "趋势研究模式",
        "en": "Trend Research Mode",
    },
    "trend_research_hint": {
        "zh": "--mode trend_research 分析的相关设置。",
        "en": "Settings for the --mode research_trend analysis.",
    },
    "trend_date_range_label": {
        "zh": "默认日期范围（天）",
        "en": "Default date range (days)",
    },
    "trend_sort_order_label": {"zh": "排序方式", "en": "Sort order"},
    "trend_max_results_label": {"zh": "最大结果数", "en": "Max results"},
    "trend_report_position_label": {
        "zh": "报告位置",
        "en": "Report position",
    },
    "generate_tldr_label": {"zh": "生成 TLDR", "en": "Generate TLDR"},
    "tldr_batch_size_label": {
        "zh": "TLDR 批次大小",
        "en": "TLDR batch size",
    },
    "enabled_skills_label": {
        "zh": "**启用的分析技能**",
        "en": "**Enabled Analysis Skills**",
    },
    # Skill names
    "skill_temporal_evolution": {
        "zh": "技术演进时间线",
        "en": "Technology Evolution Timeline",
    },
    "skill_hot_topics": {
        "zh": "热点话题聚类",
        "en": "Hot Topics Clustering",
    },
    "skill_key_authors": {
        "zh": "关键研究者分析",
        "en": "Key Researchers Analysis",
    },
    "skill_research_gaps": {
        "zh": "研究空白识别",
        "en": "Research Gap Identification",
    },
    "skill_methodology_trends": {
        "zh": "方法论趋势",
        "en": "Methodology Trends",
    },
    "skill_comprehensive_analysis": {
        "zh": "综合趋势分析",
        "en": "Comprehensive Trend Analysis",
    },
    # ── reports.py ────────────────────────────────────────────────────────
    "reports_title": {"zh": "报告查看", "en": "Report Viewer"},
    "reports_hint": {
        "zh": "浏览并在线预览所有已生成的 HTML 报告，包括每日研究报告、趋势分析报告和关键词趋势报告。",
        "en": (
            "Browse and preview all generated HTML reports: daily research, trend "
            "analysis, and keyword trend."
        ),
    },
    "reports_refresh": {"zh": "刷新文件列表", "en": "Refresh File List"},
    "reports_empty": {
        "zh": "data/reports/ 目录下暂无 HTML 报告，请先运行一次研究任务。",
        "en": "No HTML reports found in data/reports/. Run a research task first.",
    },
    "reports_empty_type": {"zh": "暂无报告", "en": "No reports"},
    "reports_count_unit": {"zh": "份", "en": "reports"},
    "reports_preview_btn": {"zh": "▶ 预览", "en": "▶ Preview"},
    "reports_dir_label": {"zh": "报告目录", "en": "Reports directory"},
    "rtype_daily": {"zh": "每日研究", "en": "Daily Research"},
    "rtype_trend": {"zh": "趋势分析", "en": "Trend Analysis"},
    "rtype_keyword_trend": {"zh": "关键词趋势", "en": "Keyword Trend"},
    "reports_meta_expander": {"zh": "运行参数", "en": "Run Parameters"},
    "meta_keyword": {"zh": "关键词", "en": "Keyword"},
    "meta_date_range": {"zh": "日期范围", "en": "Date Range"},
    "meta_papers": {"zh": "论文数量", "en": "Paper Count"},
    "reports_mtime": {"zh": "生成时间", "en": "Generated"},
    "reports_height": {"zh": "预览高度", "en": "Preview Height"},
    "reports_load_error": {"zh": "报告加载失败", "en": "Failed to load report"},
    # ── trend_runner.py 新增 i18n ──
    "tr_section_params": {"zh": "分析参数", "en": "Analysis Parameters"},
    "tr_section_run_control": {"zh": "运行控制", "en": "Run Control"},
    "tr_keywords_placeholder": {
        "zh": '例如: quantum error correction "surface code"',
        "en": 'e.g. quantum error correction "surface code"',
    },
    "tr_categories_placeholder": {
        "zh": "例如: quant-ph cs.AI（留空则不过滤）",
        "en": "e.g. quant-ph cs.AI (leave empty for no filter)",
    },
    "tr_default_date_range_days_label": {
        "zh": "默认时间范围（天）",
        "en": "Default date range (days)",
    },
    "tr_default_date_range_days_help": {
        "zh": "保存后作为新建分析的默认时间范围",
        "en": "Saved as the default date range for new analyses",
    },
    "tr_stop_btn_label": {"zh": "⏹ 停止趋势分析", "en": "⏹ Stop Trend Analysis"},
    "tr_locks_found": {
        "zh": "当前有 {n} 个趋势分析任务锁文件存在（可能正在运行或异常退出）。",
        "en": "{n} trend analysis lock file(s) found (may be running or crashed).",
    },
    "tr_stop_signal_sent": {
        "zh": "已向趋势分析进程 PID={pid} 发送停止信号 ({name})",
        "en": "Sent stop signal to trend analysis process PID={pid} ({name})",
    },
    "tr_stop_failed": {"zh": "停止 PID={pid} 失败: {err}", "en": "Failed to stop PID={pid}: {err}"},
    "tr_no_running_trend": {
        "zh": "未检测到正在运行的趋势分析进程。",
        "en": "No running trend analysis processes detected.",
    },
    "tr_err_no_keywords": {"zh": "请输入搜索关键词。", "en": "Please enter search keywords."},
    "tr_err_date_range": {
        "zh": "起始日期不能晚于截止日期。",
        "en": "Start date cannot be later than end date.",
    },
    "tr_started": {
        "zh": "趋势分析已启动！PID={pid}，请在「报告查看」Tab 中查看结果。",
        "en": "Trend analysis started! PID={pid}. Check the Reports tab for results.",
    },
    "tr_start_failed": {"zh": "启动失败: {err}", "en": "Failed to start: {err}"},
    # skill labels (also fix time_evolution and key_researchers missing earlier)
    "skill_time_evolution": {"zh": "技术演进时间线", "en": "Technology Evolution Timeline"},
    "skill_key_researchers": {"zh": "关键研究者分析", "en": "Key Researchers Analysis"},
    # run_manager 触发文件机制新 key
    "rm_docker_trigger_hint": {
        "zh": "Docker 模式：通过触发文件与主研究容器通信（安全，无需 Docker socket）",
        "en": "Docker mode: communicates with the researcher container via trigger file (no Docker socket needed)",
    },
    "rm_trigger_pending": {
        "zh": "已发送运行请求，等待主研究容器响应（最多 10 秒）...",
        "en": "Run request sent, waiting for researcher container to respond (up to 10s)...",
    },
    "rm_trigger_pending_short": {
        "zh": "等待主容器响应中...",
        "en": "Waiting for main container...",
    },
    "rm_trigger_sent": {
        "zh": "✅ 已发送运行请求！主研究容器将在 5-10 秒内启动任务，日志将在「运行日志」区实时更新。",
        "en": "✅ Run request sent! The researcher container will start the task within 5-10 seconds. Check the Run Logs section.",
    },
    "rm_trigger_failed": {
        "zh": "❌ 写入触发文件失败",
        "en": "❌ Failed to write trigger file",
    },
    "rm_already_running_warn": {
        "zh": "检测到已有一个进程在运行（PID={pid}），请先停止后再启动。",
        "en": "A process is already running (PID={pid}). Please stop it before starting a new one.",
    },
    # ── run_manager v2 新增 key ──
    "rm_trigger_stale": {
        "zh": "触发文件已存在 {n} 秒仍未被主容器消费，可能主研究容器未运行。请检查后清除。",
        "en": "Trigger file has been pending for {n}s without being consumed. The researcher container may not be running. Please check and clear it.",
    },
    "rm_clear_trigger_btn": {"zh": "🗑 清除触发文件", "en": "🗑 Clear Trigger File"},
    "rm_trigger_sent_short": {
        "zh": "已发送运行请求！主容器将在 5-10s 内启动",
        "en": "Run request sent! Container will start within 5-10s",
    },
    "rm_last_run_at": {"zh": "上次运行完成", "en": "Last run completed"},
    "rm_clean_lock_btn": {"zh": "清理", "en": "Clean"},
    "rm_clean_lock_help": {
        "zh": "删除此已停止任务的锁文件（任务已结束，锁文件残留）",
        "en": "Remove this stale lock file (task finished, file not cleaned up)",
    },
    "rm_log_group_primary": {"zh": "系统 & 运行日志", "en": "System & Run Logs"},
    "rm_log_group_secondary": {"zh": "其他日志", "en": "Other Logs"},
    "rm_log_group_system": {"zh": "系统日志", "en": "System Logs"},
    "rm_log_group_runs": {"zh": "运行日志", "en": "Run Logs"},
    "rm_no_log_selected": {
        "zh": "请从上方选择一个日志文件以查看内容。",
        "en": "Select a log file above to view its content.",
    },
    "rm_log_file_missing": {
        "zh": "⚠️ 日志文件已不存在，可能已被清理。",
        "en": "⚠️ Log file no longer exists, it may have been cleaned up.",
    },
}


def t(key: str) -> str:
    """Return the translated string for the current language."""
    lang = st.session_state.get("lang", "zh")
    entry = _TRANSLATIONS.get(key, {})
    return entry.get(lang, entry.get("en", key))
