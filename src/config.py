import os
import json
import json5  # 用于加载带注释的配置文件
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 1. 定义基础路径：获取项目根目录（src/ 的上级目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LLMConfig(BaseModel):
    """
    语言模型配置类，定义单个LLM实例的参数。

    属性:
        api_key: LLM服务的API密钥
        base_url: LLM API的基础URL，默认为OpenAI官方地址
        model_name: 使用的具体模型名称，如gpt-4o
        temperature: 模型的温度参数，控制输出的随机性（0.3为较低随机性）
    """

    api_key: str = Field(..., description="LLM服务的API密钥")
    base_url: str = Field("https://api.openai.com/v1", description="LLM API的基础URL地址")
    model_name: str = Field("gpt-4o", description="要使用的模型名称标识")
    temperature: float = 0.3


class Settings(BaseSettings):
    """
    系统全局配置类，集中管理所有应用配置参数。

    优先级：configs/config.json > .env文件 > 默认值
    """

    # ==================== 路径配置 ====================
    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # 核心数据存储目录
    REF_PDF_DIR: Path = DATA_DIR / "reference_pdfs"  # 参考论文PDF存储路径
    REPORTS_DIR: Path = DATA_DIR / "reports"  # 报告根目录（含各类型子目录）

    # 配置目录
    CONFIGS_DIR: Path = PROJECT_ROOT / "configs"

    # 报告模板目录
    REPORT_TEMPLATES_DIR: Path = CONFIGS_DIR / "templates" / "reports"

    # 从Arxiv下载的临时PDF存储目录
    DOWNLOAD_DIR: Path = DATA_DIR / "downloaded_pdfs"

    HISTORY_FILE: Path = DATA_DIR / "history.json"  # 已处理论文的历史记录文件

    # ==================== 搜索配置 ====================
    MAX_RESULTS: int = 100  # 单次搜索的最大返回结果数
    SEARCH_DAYS: int = 7  # 搜索最近N天的论文
    TARGET_DOMAINS: List[str] = ["quant-ph"]  # 目标领域列表

    # ==================== 数据源配置 ====================
    ENABLED_SOURCES: List[str] = ["arxiv"]  # 启用的数据源列表
    TARGET_JOURNALS: List[str] = []  # 目标期刊列表（如 ["prl", "pra"]）
    REPORTS_BY_SOURCE: bool = True  # 是否按数据源分目录存放报告
    HISTORY_DIR: Path = DATA_DIR / "history"  # 历史记录目录

    # OpenAlex 配置
    OPENALEX_EMAIL: str = ""  # OpenAlex 礼貌池邮箱（可选，提高速率限制）
    OPENALEX_API_KEY: str = ""  # OpenAlex API Key（可选，2026年2月后必需）

    # ArXiv 抓取配置
    ARXIV_FETCH_TIMEOUT_SECONDS: int = 180  # 单次抓取硬超时，避免无限阻塞

    # Semantic Scholar 配置
    ENABLE_SEMANTIC_SCHOLAR_TLDR: bool = True  # 是否获取AI生成的TLDR
    SEMANTIC_SCHOLAR_API_KEY: str = ""  # Semantic Scholar API Key（可选）

    # ==================== 关键词配置 ====================
    # 主要关键词（手动指定，高权重）
    PRIMARY_KEYWORDS: List[str] = []
    PRIMARY_KEYWORD_WEIGHT: float = 1.0

    # 是否启用从参考文献提取关键词
    ENABLE_REFERENCE_EXTRACTION: bool = False

    # Reference 关键词配置
    MAX_REFERENCE_KEYWORDS: int = 12
    SIMILARITY_THRESHOLD: float = 0.75  # 关键词相似度阈值
    REFERENCE_WEIGHT_HIGH: float = 0.8
    REFERENCE_WEIGHT_MEDIUM: float = 0.5
    REFERENCE_WEIGHT_LOW: float = 0.3
    REFERENCE_COUNT_HIGH: int = 3
    REFERENCE_COUNT_MEDIUM: int = 6
    REFERENCE_COUNT_LOW: int = 3

    # 研究背景上下文
    RESEARCH_CONTEXT: str = ""

    # ==================== 关键词追踪配置 ====================
    KEYWORD_TRACKER_ENABLED: bool = True
    KEYWORD_DB_PATH: Path = DATA_DIR / "keywords" / "keywords.db"
    KEYWORD_NORMALIZATION_ENABLED: bool = True
    KEYWORD_NORMALIZATION_BATCH_SIZE: int = 50
    KEYWORD_TREND_DEFAULT_DAYS: int = 30
    KEYWORD_CHART_TOP_N: int = 15
    KEYWORD_TREND_TOP_N: int = 5
    KEYWORD_REPORT_ENABLED: bool = True
    KEYWORD_REPORT_FREQUENCY: str = "weekly"  # daily, weekly, monthly, always

    # ==================== 通知配置 ====================
    ENABLE_NOTIFICATIONS: bool = False

    # SMTP 邮件配置
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""  # 发件人地址，默认使用 SMTP_USER
    SMTP_TO: str = ""  # 收件人地址，逗号分隔多个
    SMTP_USE_TLS: bool = True

    # Webhook 配置
    WECHAT_WEBHOOK_URL: str = ""  # 企业微信机器人 Webhook URL
    DINGTALK_WEBHOOK_URL: str = ""  # 钉钉机器人 Webhook URL
    DINGTALK_SECRET: str = ""  # 钉钉机器人签名密钥（可选）
    TELEGRAM_BOT_TOKEN: str = ""  # Telegram Bot Token
    TELEGRAM_CHAT_ID: str = ""  # Telegram Chat ID
    SLACK_WEBHOOK_URL: str = ""  # Slack Incoming Webhook URL
    GENERIC_WEBHOOK_URL: str = ""  # 通用 Webhook URL

    # 通知偏好
    NOTIFY_ON_SUCCESS: bool = True  # 成功时发送通知
    NOTIFY_ON_FAILURE: bool = True  # 失败时发送通知
    NOTIFY_ATTACH_REPORTS: bool = False  # 邮件是否附带报告文件

    # 各渠道独立开关（需同时在 .env 中配置对应密钥才会生效）
    NOTIFY_EMAIL_ENABLED: bool = True
    NOTIFY_WECHAT_ENABLED: bool = True
    NOTIFY_DINGTALK_ENABLED: bool = True
    NOTIFY_TELEGRAM_ENABLED: bool = True
    NOTIFY_SLACK_ENABLED: bool = True
    NOTIFY_GENERIC_WEBHOOK_ENABLED: bool = True

    # ==================== 重试配置 ====================
    RETRY_MAX_ATTEMPTS: int = 3  # 最大重试次数
    RETRY_MIN_WAIT: int = 2  # 最小等待时间（秒），指数退避起始值
    RETRY_MAX_WAIT: int = 30  # 最大等待时间（秒）

    # ==================== 日志配置 ====================
    LOG_KEEP_DAYS: int = 30  # 日志保留天数
    LOG_ROTATION_TYPE: str = "time"  # "time" (按天轮换) 或 "size" (按大小轮换)

    # ==================== 并发配置 ====================
    ENABLE_CONCURRENCY: bool = False  # 是否启用并发
    CONCURRENCY_WORKERS: int = 3  # 并发线程数（建议不超过5）

    # ==================== LLM 请求池配置 ====================
    LLM_REQUEST_POOL_ENABLED: bool = True
    LLM_REQUESTS_PER_MINUTE: int = 10
    LLM_REQUEST_POOL_LOG_SLOW_WAIT_SECONDS: float = 1.0

    # ==================== 报告配置 ====================
    ENABLE_HTML_REPORT: bool = True  # 是否同时生成HTML格式报告
    ENABLE_MARKDOWN_REPORT: bool = True  # 是否生成Markdown格式报告
    TOKEN_TRACKING_ENABLED: bool = True  # 是否在报告和通知中显示 token 消耗统计

    # ==================== Daily Research 模式配置 ====================
    DAILY_ENABLE_DEEP_ANALYSIS: bool = True  # 是否在每日研究模式中执行深度分析

    # ==================== PDF 解析配置 ====================
    PDF_PARSER_MODE: str = "mineru"  # PDF 解析模式: "mineru" (云端API) 或 "pymupdf" (本地解析)
    MINERU_API_KEY: str = ""  # MinerU API Token
    MINERU_MODEL_VERSION: str = "pipeline"  # MinerU 模型版本: pipeline 或 vlm
    MINERU_POLL_INTERVAL: int = 3  # MinerU 任务状态轮询间隔（秒）
    MINERU_POLL_TIMEOUT: int = 300  # MinerU 任务超时时间（秒）

    # ==================== 自动更新配置 ====================
    AUTO_UPDATE_ENABLED: bool = True  # 是否启用自动更新检查

    # ==================== 网络代理配置 ====================
    PROXY_ENABLED: bool = False  # 是否启用网络代理
    PROXY_URL: str = ""  # 代理地址，如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080
    PROXY_NO_PROXY: str = "localhost,127.0.0.1"  # 不使用代理的地址列表
    # 各服务独立代理开关
    PROXY_ARXIV: bool = True  # ArXiv API 是否使用代理
    PROXY_OPENALEX: bool = False  # OpenAlex API 是否使用代理
    PROXY_SEMANTIC_SCHOLAR: bool = False  # Semantic Scholar API 是否使用代理
    PROXY_LLM_API: bool = False  # LLM API 是否使用代理
    PROXY_NOTIFICATIONS: bool = False  # 通知 Webhook 是否使用代理
    PROXY_UPDATE_CHECK: bool = False  # 检查更新是否使用代理

    # ==================== WebDAV 同步配置 ====================
    WEBDAV_ENABLED: bool = False  # 是否启用 WebDAV 同步
    WEBDAV_URL: str = ""  # WebDAV 服务器地址（从 .env 加载）
    WEBDAV_USERNAME: str = ""  # WebDAV 用户名（从 .env 加载）
    WEBDAV_PASSWORD: str = ""  # WebDAV 密码（从 .env 加载）
    WEBDAV_REMOTE_PATH: str = "/arxiv-daily-researcher/"  # 远程存储根路径
    WEBDAV_SYNC_MODE: str = "after_report"  # 同步模式: manual / scheduled / after_report
    WEBDAV_CRON_SCHEDULE: str = "0 23 * * *"  # 定时同步 cron 表达式
    WEBDAV_SYNC_CONFIGS: bool = True  # 是否同步配置文件
    WEBDAV_SYNC_HISTORY: bool = True  # 是否同步历史记录
    WEBDAV_SYNC_KEYWORDS: bool = True  # 是否同步关键词数据
    WEBDAV_SYNC_REPORTS: bool = False  # 是否同步报告（体积较大）

    # ==================== 运行锁配置 ====================
    RUN_LOCK_MAX_AGE_HOURS: int = 12  # 锁超龄阈值（小时），超时将尝试回收卡死任务

    # ==================== 通知扩展 ====================
    NOTIFICATION_TOP_N: int = 5  # 通知中包含的Top-N高分论文数量

    # ==================== 搜索扩展 ====================
    MAX_RESULTS_PER_SOURCE: Dict[str, int] = {}  # 按数据源单独配置max_results

    # ==================== 评分配置 ====================
    # 关键词相关度评分
    MAX_SCORE_PER_KEYWORD: int = 10

    # 作者附加分
    ENABLE_AUTHOR_BONUS: bool = True
    EXPERT_AUTHORS: List[str] = []
    AUTHOR_BONUS_POINTS: float = 5.0

    # 动态及格分公式参数
    PASSING_SCORE_BASE: float = 3.0
    PASSING_SCORE_WEIGHT_COEFFICIENT: float = 2.5

    # 报告配置
    INCLUDE_ALL_IN_REPORT: bool = True

    # 评分策略配置
    SCORING_METHOD: str = "keyword_weighted"
    MLSYS_COMMITTEE_MODELS: List[str] = [
        "minimax-m2.7",
        "qwen3.5-27b",
        "deepseek-v3.2",
    ]
    MLSYS_PASSING_SCORE: float = 6.0
    MLSYS_FALLBACK_SCORE: float = 5.0
    MLSYS_CIRCUIT_BREAKER_THRESHOLD: int = 3
    MLSYS_EXPORT_ARTIFACTS: bool = True
    MLSYS_SMART_REVIEW_ENABLED: bool = True
    MLSYS_SMART_REVIEW_MIN_SCORE: float = 5.0
    MLSYS_SMART_REVIEW_MAX_SCORE: float = 7.0

    # ==================== LLM配置 ====================
    # 低成本LLM：用于快速初步筛选和关键词生成
    CHEAP_LLM: LLMConfig = Field(default_factory=lambda: LLMConfig(api_key="sk-dummy"))
    # 高性能LLM：用于深层论文分析和内容理解
    SMART_LLM: LLMConfig = Field(default_factory=lambda: LLMConfig(api_key="sk-dummy"))

    # ==================== 研究趋势模式配置 ====================
    RESEARCH_REPORTS_DIR: Path = DATA_DIR / "reports" / "trend_research"  # 研究趋势报告存储路径
    RESEARCH_DEFAULT_DATE_RANGE_DAYS: int = 365  # 默认搜索时间范围（天）
    RESEARCH_MAX_RESULTS: int = 500  # 最大论文数（安全上限）
    RESEARCH_SORT_ORDER: str = "ascending"  # 时间排序："ascending"(旧→新) 或 "descending"(新→旧)
    RESEARCH_REPORT_POSITION: str = "end"  # 趋势分析在报告中的位置："beginning" 或 "end"
    RESEARCH_GENERATE_TLDR: bool = True  # 是否为每篇论文生成 LLM TLDR
    RESEARCH_TLDR_BATCH_SIZE: int = 10  # TLDR 批量并发大小
    RESEARCH_OUTPUT_FORMATS: List[str] = ["markdown", "html"]  # 输出格式
    RESEARCH_ENABLED_SKILLS: List[str] = [  # 启用的趋势分析技能
        "comprehensive_analysis",
    ]

    # ==================== Pydantic Settings配置 ====================
    # 指定从.env文件加载配置，支持嵌套参数用双下划线分隔
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # 嵌套配置使用__分隔符，如CHEAP_LLM__API_KEY
        extra="ignore",  # 忽略.env中未定义的额外参数
    )

    def load_from_search_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        从 configs/config.json 加载配置并覆盖默认值。

        注意：LLM 配置完全从 .env 文件加载，不从此配置文件加载。

        参数:
            config_path: 配置文件路径，默认为 PROJECT_ROOT/configs/config.json

        返回:
            dict: 配置字典
        """
        if config_path is None:
            config_path = self.PROJECT_ROOT / "configs" / "config.json"

        if not config_path.exists():
            print(f"警告: 未找到配置文件 {config_path}，使用默认配置")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json5.load(f)  # 使用json5支持注释

            # 加载搜索设置
            if "search_settings" in config:
                settings = config["search_settings"]
                self.SEARCH_DAYS = settings.get("search_days", self.SEARCH_DAYS)
                self.MAX_RESULTS = settings.get("max_results", self.MAX_RESULTS)
                self.MAX_RESULTS_PER_SOURCE = settings.get("max_results_per_source", {})

            # 加载目标领域
            if "target_domains" in config:
                domains = config["target_domains"].get("domains", [])
                if domains:
                    self.TARGET_DOMAINS = domains

            # 加载数据源配置
            if "data_sources" in config:
                ds_config = config["data_sources"]
                self.ENABLED_SOURCES = ds_config.get("enabled", ["arxiv"])
                self.TARGET_JOURNALS = ds_config.get("journals", [])
                self.REPORTS_BY_SOURCE = ds_config.get("reports_by_source", True)
                if "arxiv" in ds_config:
                    arxiv_cfg = ds_config["arxiv"]
                    if isinstance(arxiv_cfg, dict):
                        self.ARXIV_FETCH_TIMEOUT_SECONDS = arxiv_cfg.get(
                            "fetch_timeout_seconds", self.ARXIV_FETCH_TIMEOUT_SECONDS
                        )

            # 加载关键词配置
            if "keywords" in config:
                kw_config = config["keywords"]

                # 主要关键词
                if "primary_keywords" in kw_config:
                    pk = kw_config["primary_keywords"]
                    self.PRIMARY_KEYWORDS = pk.get("keywords", [])
                    self.PRIMARY_KEYWORD_WEIGHT = pk.get("weight", 1.0)

                # Reference 提取配置
                self.ENABLE_REFERENCE_EXTRACTION = kw_config.get(
                    "enable_reference_extraction", False
                )

                if "reference_keywords_config" in kw_config:
                    ref_cfg = kw_config["reference_keywords_config"]
                    self.MAX_REFERENCE_KEYWORDS = ref_cfg.get("max_keywords", 12)
                    self.SIMILARITY_THRESHOLD = ref_cfg.get("similarity_threshold", 0.75)

                    weight_dist = ref_cfg.get("weight_distribution", {})
                    if "high_importance" in weight_dist:
                        self.REFERENCE_WEIGHT_HIGH = weight_dist["high_importance"].get(
                            "weight", 0.8
                        )
                        self.REFERENCE_COUNT_HIGH = weight_dist["high_importance"].get("count", 3)
                    if "medium_importance" in weight_dist:
                        self.REFERENCE_WEIGHT_MEDIUM = weight_dist["medium_importance"].get(
                            "weight", 0.5
                        )
                        self.REFERENCE_COUNT_MEDIUM = weight_dist["medium_importance"].get(
                            "count", 6
                        )
                    if "low_importance" in weight_dist:
                        self.REFERENCE_WEIGHT_LOW = weight_dist["low_importance"].get("weight", 0.3)
                        self.REFERENCE_COUNT_LOW = weight_dist["low_importance"].get("count", 3)

                # 研究背景
                self.RESEARCH_CONTEXT = kw_config.get("research_context", "")

            # 加载评分设置
            if "scoring_settings" in config:
                score_cfg = config["scoring_settings"]

                # 关键词相关度评分
                if "keyword_relevance_score" in score_cfg:
                    self.MAX_SCORE_PER_KEYWORD = score_cfg["keyword_relevance_score"].get(
                        "max_score_per_keyword", 10
                    )

                # 作者附加分
                if "author_bonus" in score_cfg:
                    ab = score_cfg["author_bonus"]
                    self.ENABLE_AUTHOR_BONUS = ab.get("enabled", True)
                    self.EXPERT_AUTHORS = ab.get("expert_authors", [])
                    self.AUTHOR_BONUS_POINTS = ab.get("bonus_points", 5.0)

                # 动态及格分公式
                if "passing_score_formula" in score_cfg:
                    psf = score_cfg["passing_score_formula"]
                    self.PASSING_SCORE_BASE = psf.get("base_score", 3.0)
                    self.PASSING_SCORE_WEIGHT_COEFFICIENT = psf.get("weight_coefficient", 2.5)

                # 报告配置
                self.INCLUDE_ALL_IN_REPORT = score_cfg.get("include_all_in_report", True)

                # 评分策略
                self.SCORING_METHOD = score_cfg.get("strategy", self.SCORING_METHOD)

                if "mlsys_multi_model" in score_cfg:
                    committee_cfg = score_cfg["mlsys_multi_model"]
                    self.MLSYS_COMMITTEE_MODELS = committee_cfg.get(
                        "committee_models", self.MLSYS_COMMITTEE_MODELS
                    )
                    self.MLSYS_PASSING_SCORE = committee_cfg.get(
                        "passing_score", self.MLSYS_PASSING_SCORE
                    )
                    self.MLSYS_FALLBACK_SCORE = committee_cfg.get(
                        "fallback_score", self.MLSYS_FALLBACK_SCORE
                    )
                    self.MLSYS_CIRCUIT_BREAKER_THRESHOLD = committee_cfg.get(
                        "circuit_breaker_threshold", self.MLSYS_CIRCUIT_BREAKER_THRESHOLD
                    )
                    self.MLSYS_EXPORT_ARTIFACTS = committee_cfg.get(
                        "export_artifacts", self.MLSYS_EXPORT_ARTIFACTS
                    )
                    smart_review_cfg = committee_cfg.get("smart_review", {})
                    self.MLSYS_SMART_REVIEW_ENABLED = smart_review_cfg.get(
                        "enabled", self.MLSYS_SMART_REVIEW_ENABLED
                    )
                    self.MLSYS_SMART_REVIEW_MIN_SCORE = smart_review_cfg.get(
                        "min_preliminary_score", self.MLSYS_SMART_REVIEW_MIN_SCORE
                    )
                    self.MLSYS_SMART_REVIEW_MAX_SCORE = smart_review_cfg.get(
                        "max_preliminary_score", self.MLSYS_SMART_REVIEW_MAX_SCORE
                    )

            # 加载路径配置
            if "paths" in config:
                paths = config["paths"]
                if "data_dir" in paths:
                    self.DATA_DIR = self.PROJECT_ROOT / paths["data_dir"]
                if "reference_pdfs" in paths:
                    self.REF_PDF_DIR = self.PROJECT_ROOT / paths["reference_pdfs"]
                if "reports" in paths:
                    self.REPORTS_DIR = self.PROJECT_ROOT / paths["reports"]
                    self.RESEARCH_REPORTS_DIR = self.REPORTS_DIR / "trend_research"
                if "downloaded_pdfs" in paths:
                    self.DOWNLOAD_DIR = self.PROJECT_ROOT / paths["downloaded_pdfs"]
                if "history_file" in paths:
                    self.HISTORY_FILE = self.PROJECT_ROOT / paths["history_file"]

            # 加载关键词追踪配置
            if "keyword_tracker" in config:
                kt = config["keyword_tracker"]
                self.KEYWORD_TRACKER_ENABLED = kt.get("enabled", True)

                if "database" in kt:
                    db_path = kt["database"].get("path", "data/keywords/keywords.db")
                    self.KEYWORD_DB_PATH = self.PROJECT_ROOT / db_path

                if "normalization" in kt:
                    norm = kt["normalization"]
                    self.KEYWORD_NORMALIZATION_ENABLED = norm.get("enabled", True)
                    self.KEYWORD_NORMALIZATION_BATCH_SIZE = norm.get("batch_size", 25)

                if "trend_view" in kt:
                    self.KEYWORD_TREND_DEFAULT_DAYS = kt["trend_view"].get("default_days", 30)

                if "charts" in kt:
                    charts = kt["charts"]
                    if "bar_chart" in charts:
                        self.KEYWORD_CHART_TOP_N = charts["bar_chart"].get("top_n", 15)
                    if "trend_chart" in charts:
                        self.KEYWORD_TREND_TOP_N = charts["trend_chart"].get("top_n", 5)

                if "report" in kt:
                    report_cfg = kt["report"]
                    self.KEYWORD_REPORT_ENABLED = report_cfg.get("enabled", True)
                    self.KEYWORD_REPORT_FREQUENCY = report_cfg.get("frequency", "weekly")

            # 加载通知配置
            if "notifications" in config:
                notif = config["notifications"]
                self.ENABLE_NOTIFICATIONS = notif.get("enabled", False)
                self.NOTIFY_ON_SUCCESS = notif.get("on_success", True)
                self.NOTIFY_ON_FAILURE = notif.get("on_failure", True)
                self.NOTIFY_ATTACH_REPORTS = notif.get("attach_reports", False)
                self.NOTIFICATION_TOP_N = notif.get("top_n", 5)

                # 各渠道独立开关
                channels = notif.get("channels", {})
                self.NOTIFY_EMAIL_ENABLED = channels.get("email", {}).get("enabled", True)
                self.NOTIFY_WECHAT_ENABLED = channels.get("wechat_work", {}).get("enabled", True)
                self.NOTIFY_DINGTALK_ENABLED = channels.get("dingtalk", {}).get("enabled", True)
                self.NOTIFY_TELEGRAM_ENABLED = channels.get("telegram", {}).get("enabled", True)
                self.NOTIFY_SLACK_ENABLED = channels.get("slack", {}).get("enabled", True)
                self.NOTIFY_GENERIC_WEBHOOK_ENABLED = channels.get("generic_webhook", {}).get(
                    "enabled", True
                )

            # 加载重试配置
            if "retry" in config:
                retry_cfg = config["retry"]
                self.RETRY_MAX_ATTEMPTS = retry_cfg.get("max_attempts", 3)
                self.RETRY_MIN_WAIT = retry_cfg.get("min_wait", 2)
                self.RETRY_MAX_WAIT = retry_cfg.get("max_wait", 30)

            # 加载日志配置
            if "logging" in config:
                log_cfg = config["logging"]
                self.LOG_KEEP_DAYS = log_cfg.get("keep_days", 30)
                self.LOG_ROTATION_TYPE = log_cfg.get("rotation_type", "time")

            # 加载并发配置
            if "concurrency" in config:
                conc_cfg = config["concurrency"]
                self.ENABLE_CONCURRENCY = conc_cfg.get("enabled", False)
                self.CONCURRENCY_WORKERS = conc_cfg.get("workers", 3)

            # 加载 LLM 请求池配置
            if "llm_request_pool" in config:
                pool_cfg = config["llm_request_pool"]
                self.LLM_REQUEST_POOL_ENABLED = pool_cfg.get(
                    "enabled", self.LLM_REQUEST_POOL_ENABLED
                )
                self.LLM_REQUESTS_PER_MINUTE = pool_cfg.get(
                    "requests_per_minute", self.LLM_REQUESTS_PER_MINUTE
                )
                self.LLM_REQUEST_POOL_LOG_SLOW_WAIT_SECONDS = pool_cfg.get(
                    "log_slow_wait_seconds", self.LLM_REQUEST_POOL_LOG_SLOW_WAIT_SECONDS
                )

            # 加载报告设置
            if "report_settings" in config:
                rpt_cfg = config["report_settings"]
                self.ENABLE_HTML_REPORT = rpt_cfg.get("enable_html_report", False)
                self.ENABLE_MARKDOWN_REPORT = rpt_cfg.get("enable_markdown_report", True)

            # 加载 daily research 模式配置
            if "daily_research" in config:
                daily_cfg = config["daily_research"]
                self.DAILY_ENABLE_DEEP_ANALYSIS = daily_cfg.get(
                    "enable_deep_analysis", True
                )

            # 加载 PDF 解析配置
            if "pdf_parser" in config:
                pdf_cfg = config["pdf_parser"]
                self.PDF_PARSER_MODE = pdf_cfg.get("mode", "mineru")
                self.MINERU_MODEL_VERSION = pdf_cfg.get("mineru_model_version", "pipeline")
                self.MINERU_POLL_INTERVAL = pdf_cfg.get("poll_interval", 3)
                self.MINERU_POLL_TIMEOUT = pdf_cfg.get("poll_timeout", 300)

            # 加载自动更新配置
            if "auto_update" in config:
                au_cfg = config["auto_update"]
                self.AUTO_UPDATE_ENABLED = au_cfg.get("enabled", True)

            # 加载运行锁配置
            if "run_lock" in config:
                lock_cfg = config["run_lock"]
                self.RUN_LOCK_MAX_AGE_HOURS = lock_cfg.get(
                    "max_age_hours", self.RUN_LOCK_MAX_AGE_HOURS
                )

            # 加载 token 追踪配置
            if "token_tracking" in config:
                tt_cfg = config["token_tracking"]
                self.TOKEN_TRACKING_ENABLED = tt_cfg.get("enabled", True)

            # 加载网络代理配置
            if "proxy" in config:
                px_cfg = config["proxy"]
                self.PROXY_ENABLED = px_cfg.get("enabled", False)
                self.PROXY_URL = px_cfg.get("url", "")
                self.PROXY_NO_PROXY = px_cfg.get("no_proxy", "localhost,127.0.0.1")
                scope = px_cfg.get("scope", {})
                self.PROXY_ARXIV = scope.get("arxiv", True)
                self.PROXY_OPENALEX = scope.get("openalex", False)
                self.PROXY_SEMANTIC_SCHOLAR = scope.get("semantic_scholar", False)
                self.PROXY_LLM_API = scope.get("llm_api", False)
                self.PROXY_NOTIFICATIONS = scope.get("notifications", False)
                self.PROXY_UPDATE_CHECK = scope.get("update_check", False)

            # 加载 WebDAV 同步配置（仅同步设置，凭据从 .env 加载）
            if "webdav" in config:
                wd_cfg = config["webdav"]
                self.WEBDAV_ENABLED = wd_cfg.get("enabled", False)
                self.WEBDAV_REMOTE_PATH = wd_cfg.get("remote_path", "/arxiv-daily-researcher/")
                self.WEBDAV_SYNC_MODE = wd_cfg.get("sync_mode", "after_report")
                self.WEBDAV_CRON_SCHEDULE = wd_cfg.get("cron_schedule", "0 23 * * *")
                self.WEBDAV_SYNC_CONFIGS = wd_cfg.get("sync_configs", True)
                self.WEBDAV_SYNC_HISTORY = wd_cfg.get("sync_history", True)
                self.WEBDAV_SYNC_KEYWORDS = wd_cfg.get("sync_keywords", True)
                self.WEBDAV_SYNC_REPORTS = wd_cfg.get("sync_reports", False)

            # 加载研究趋势模式配置
            if "trend_research" in config:
                tr = config["trend_research"]
                self.RESEARCH_DEFAULT_DATE_RANGE_DAYS = tr.get("default_date_range_days", 365)
                self.RESEARCH_MAX_RESULTS = tr.get("max_results", 500)
                self.RESEARCH_SORT_ORDER = tr.get("sort_order", "ascending")
                self.RESEARCH_REPORT_POSITION = tr.get("report_position", "end")
                self.RESEARCH_GENERATE_TLDR = tr.get("generate_tldr", True)
                self.RESEARCH_TLDR_BATCH_SIZE = tr.get("tldr_batch_size", 10)
                self.RESEARCH_OUTPUT_FORMATS = tr.get("output_formats", ["markdown", "html"])
                self.RESEARCH_ENABLED_SKILLS = tr.get(
                    "enabled_skills",
                    [
                        "temporal_evolution",
                        "hot_topics",
                        "key_authors",
                        "research_gaps",
                        "methodology_trends",
                    ],
                )

            return config

        except Exception as e:
            print(f"加载 configs/config.json 失败: {e}")
            import traceback

            traceback.print_exc()
            return {}

    def get_proxy_dict(self, service: str = "") -> Optional[Dict[str, str]]:
        """
        获取指定服务的代理配置字典，适用于 requests.Session.proxies。

        参数:
            service: 服务名，如 "arxiv"、"openalex"、"semantic_scholar"、"llm_api"、"notifications"
                     空字符串表示仅检查全局开关

        返回:
            Dict[str, str]: 代理字典 {"http": url, "https": url}，未启用时返回 None
        """
        if not self.PROXY_ENABLED or not self.PROXY_URL:
            return None

        # 检查服务级别的开关
        scope_map = {
            "arxiv": self.PROXY_ARXIV,
            "openalex": self.PROXY_OPENALEX,
            "semantic_scholar": self.PROXY_SEMANTIC_SCHOLAR,
            "llm_api": self.PROXY_LLM_API,
            "notifications": self.PROXY_NOTIFICATIONS,
            "update_check": self.PROXY_UPDATE_CHECK,
        }

        if service and not scope_map.get(service, False):
            return None

        proxy_url = self.PROXY_URL.strip()
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    def get_merged_keywords(self) -> Dict[str, float]:
        """
        获取合并后的关键词字典（关键词 -> 权重）

        返回:
            dict: {关键词: 权重}
        """
        keywords_dict = {}

        # 添加主要关键词
        for kw in self.PRIMARY_KEYWORDS:
            keywords_dict[kw] = self.PRIMARY_KEYWORD_WEIGHT

        return keywords_dict

    def calculate_passing_score(self, total_keyword_weight: float) -> float:
        """
        计算动态及格分

        公式: 及格分 = base_score + coefficient × Σ(关键词权重)

        参数:
            total_keyword_weight: 所有关键词权重之和

        返回:
            float: 及格分数
        """
        return (
            self.PASSING_SCORE_BASE + self.PASSING_SCORE_WEIGHT_COEFFICIENT * total_keyword_weight
        )

    @staticmethod
    def _split_model_names(raw_value: Any) -> List[str]:
        """将单个模型名或逗号分隔的模型名字符串解析为列表。"""
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        if raw_value is None:
            return []
        return [part.strip() for part in str(raw_value).split(",") if part.strip()]

    def apply_llm_model_overrides(self) -> None:
        """
        规范化 .env 中的模型名配置。

        - CHEAP_LLM__MODEL_NAME 支持逗号分隔的多模型写法；
        - 在 MLSys 委员会评分模式下，多模型列表会覆盖委员会模型配置；
        - 其他使用 CHEAP_LLM 的功能默认取第一个模型，避免把逗号拼接串直接传给 API。
        """
        cheap_models = self._split_model_names(self.CHEAP_LLM.model_name)
        if cheap_models:
            if self.is_committee_scoring_enabled() and len(cheap_models) > 1:
                self.MLSYS_COMMITTEE_MODELS = cheap_models
            self.CHEAP_LLM.model_name = cheap_models[0]

        smart_models = self._split_model_names(self.SMART_LLM.model_name)
        if smart_models:
            self.SMART_LLM.model_name = smart_models[0]

    def is_committee_scoring_enabled(self) -> bool:
        """是否启用 MLSys 多模型委员会评分。"""
        return self.SCORING_METHOD == "mlsys_multi_model"

    def ensure_directories(self):
        """
        确保所有必需的目录存在。
        如果目录不存在则自动创建（递归创建上级目录）。
        """
        self.REF_PDF_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (self.REPORTS_DIR / "keyword_trend").mkdir(parents=True, exist_ok=True)
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORT_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    def load_report_css(self, css_name: str = "html_report.css") -> str:
        """
        加载 HTML 报告的 CSS 样式文件。

        参数:
            css_name: CSS 文件名，默认为 html_report.css

        返回:
            str: CSS 样式字符串，文件不存在时返回空字符串
        """
        css_path = self.REPORT_TEMPLATES_DIR / css_name

        if not css_path.exists():
            print(f"警告: 未找到 CSS 样式文件 {css_path}，将使用空样式")
            return ""

        try:
            with open(css_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"加载 CSS 样式文件 {css_name} 失败: {e}")
            return ""

    def load_report_template(
        self, template_name: str = "basic_report_template.json"
    ) -> Dict[str, Any]:
        """
        加载报告模板配置。

        参数:
            template_name: 模板文件名

        返回:
            dict: 模板配置字典
        """
        template_path = self.REPORT_TEMPLATES_DIR / template_name

        if not template_path.exists():
            print(f"警告: 未找到报告模板文件 {template_path}")
            return {}

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return json5.load(f)  # 使用json5支持注释
        except Exception as e:
            print(f"加载报告模板 {template_name} 失败: {e}")
            return {}


# 实例化全局配置单例对象，应用程序全局共享
settings = Settings()

# 从 configs/config.json 加载配置（会覆盖默认值）
settings.load_from_search_config()
settings.apply_llm_model_overrides()

# 自动创建所有必需的工作目录
settings.ensure_directories()
