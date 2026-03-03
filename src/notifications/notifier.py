"""
通知代理模块 - 多渠道通知系统

支持的通知渠道：
- Email: SMTP 邮件通知
- 企业微信: Webhook 机器人（Markdown 模板）
- 钉钉: Webhook 机器人（支持签名验证）
- Telegram: Bot API
- Slack: Incoming Webhook
- 通用 Webhook: 自定义 URL

支持的通知类型：
- 运行成功/失败通知（基于可自定义模板）
- 错误告警通知（MinerU、LLM、网络、通用错误）
"""

import json
import logging
import smtplib
import hashlib
import hmac
import base64
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Dict, Optional, Any

import requests

logger = logging.getLogger(__name__)

# 模板目录
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "notification_templates"


def _load_template(name: str) -> Optional[str]:
    """
    加载通知模板文件。

    模板文件存放于 configs/notification_templates/ 目录，
    以 '# ' 开头（单个 #）的行视为注释，不会出现在最终消息中。
    '## ' 及更多 # 开头的行保留为 Markdown 标题。

    参数:
        name: 模板文件名（不含扩展名），如 'success'、'error_mineru'

    返回:
        去除注释后的模板内容，文件不存在时返回 None
    """
    path = TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        logger.debug(f"模板文件不存在: {path}")
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        content_lines = []
        for line in lines:
            stripped = line.lstrip()
            # 单 # 开头且不是 ## 的行视为注释
            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue
            if stripped == "#":
                continue
            content_lines.append(line)
        return "\n".join(content_lines).strip()
    except Exception as e:
        logger.warning(f"加载模板失败 ({path}): {e}")
        return None


def _render_template(template: str, **kwargs) -> str:
    """渲染模板，将 {变量名} 替换为实际值。未提供的变量保留原样。"""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


@dataclass
class RunResult:
    """管道运行结果摘要"""
    run_timestamp: str = ""
    total_papers_fetched: int = 0
    papers_by_source: Dict[str, int] = field(default_factory=dict)
    qualified_by_source: Dict[str, int] = field(default_factory=dict)
    analyzed_by_source: Dict[str, int] = field(default_factory=dict)
    report_paths: Dict[str, str] = field(default_factory=dict)
    total_qualified: int = 0
    total_analyzed: int = 0
    success: bool = True
    error_message: Optional[str] = None
    top_papers: List[Dict[str, Any]] = field(default_factory=list)


class BaseNotifier(ABC):
    """通知器抽象基类"""

    @abstractmethod
    def send(self, subject: str, body: str,
             attachments: Optional[List[Path]] = None) -> bool:
        """发送通知，成功返回 True"""
        ...


class EmailNotifier(BaseNotifier):
    """SMTP 邮件通知"""

    def __init__(self, host: str, port: int, user: str, password: str,
                 from_addr: str, to_addrs: List[str], use_tls: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr or user
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    def send(self, subject: str, body: str,
             attachments: Optional[List[Path]] = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = subject

        # 正文
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # 附件
        if attachments:
            for filepath in attachments:
                if filepath.exists() and filepath.is_file():
                    part = MIMEBase("application", "octet-stream")
                    with open(filepath, "rb") as f:
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={filepath.name}"
                    )
                    msg.attach(part)

        # 发送
        if self.port == 465:
            # SSL 直连
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as server:
                server.login(self.user, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
        else:
            # STARTTLS
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())

        logger.info(f"邮件已发送至: {', '.join(self.to_addrs)}")
        return True


class WebhookNotifier(BaseNotifier):
    """多平台 Webhook 通知"""

    def __init__(self, platform: str, webhook_url: str, **kwargs):
        self.platform = platform
        self.webhook_url = webhook_url
        self.extra = kwargs  # secret, chat_id 等

    def send(self, subject: str, body: str,
             attachments: Optional[List[Path]] = None) -> bool:
        formatter = getattr(self, f"_format_{self.platform}", self._format_generic)
        url, payload, headers = formatter(subject, body)
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        logger.info(f"Webhook [{self.platform}] 通知已发送")
        return True

    def _format_wechat_work(self, subject: str, body: str):
        """企业微信机器人 — body 已含完整 Markdown 模板内容"""
        content = body
        # 企业微信 markdown 限制 4096 字节
        if len(content.encode("utf-8")) > 4000:
            content = content[:1300] + "\n\n...(内容已截断)"
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        return self.webhook_url, payload, {"Content-Type": "application/json"}

    def _format_dingtalk(self, subject: str, body: str):
        """钉钉机器人（支持签名验证）"""
        url = self.webhook_url
        secret = self.extra.get("secret", "")
        if secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": subject,
                "text": body
            }
        }
        return url, payload, {"Content-Type": "application/json"}

    def _format_telegram(self, subject: str, body: str):
        """Telegram Bot"""
        chat_id = self.extra.get("chat_id", "")
        text = f"*{subject}*\n\n{body}"
        # Telegram 消息限 4096 字符
        if len(text) > 4000:
            text = text[:3900] + "\n\n...(内容已截断)"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        return self.webhook_url, payload, {"Content-Type": "application/json"}

    def _format_slack(self, subject: str, body: str):
        """Slack Incoming Webhook"""
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": subject}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": body}
                }
            ]
        }
        return self.webhook_url, payload, {"Content-Type": "application/json"}

    def _format_generic(self, subject: str, body: str):
        """通用 Webhook"""
        payload = {
            "subject": subject,
            "body": body,
            "timestamp": datetime.now().isoformat()
        }
        return self.webhook_url, payload, {"Content-Type": "application/json"}


class NotifierAgent:
    """通知编排代理，管理所有已配置的通知渠道"""

    def __init__(self):
        from config import settings
        self.settings = settings
        self.notifiers: List[BaseNotifier] = []
        self._setup_notifiers()

    def _setup_notifiers(self):
        """根据配置初始化通知渠道"""
        s = self.settings

        # Email
        if s.SMTP_HOST and s.SMTP_TO:
            to_addrs = [a.strip() for a in s.SMTP_TO.split(",") if a.strip()]
            self.notifiers.append(EmailNotifier(
                host=s.SMTP_HOST, port=s.SMTP_PORT,
                user=s.SMTP_USER, password=s.SMTP_PASSWORD,
                from_addr=s.SMTP_FROM, to_addrs=to_addrs,
                use_tls=s.SMTP_USE_TLS
            ))
            logger.info("已启用邮件通知")

        # 企业微信
        if s.WECHAT_WEBHOOK_URL:
            self.notifiers.append(
                WebhookNotifier("wechat_work", s.WECHAT_WEBHOOK_URL))
            logger.info("已启用企业微信通知")

        # 钉钉
        if s.DINGTALK_WEBHOOK_URL:
            self.notifiers.append(
                WebhookNotifier("dingtalk", s.DINGTALK_WEBHOOK_URL,
                                secret=s.DINGTALK_SECRET))
            logger.info("已启用钉钉通知")

        # Telegram
        if s.TELEGRAM_BOT_TOKEN and s.TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{s.TELEGRAM_BOT_TOKEN}/sendMessage"
            self.notifiers.append(
                WebhookNotifier("telegram", url, chat_id=s.TELEGRAM_CHAT_ID))
            logger.info("已启用 Telegram 通知")

        # Slack
        if s.SLACK_WEBHOOK_URL:
            self.notifiers.append(
                WebhookNotifier("slack", s.SLACK_WEBHOOK_URL))
            logger.info("已启用 Slack 通知")

        # 通用 Webhook
        if s.GENERIC_WEBHOOK_URL:
            self.notifiers.append(
                WebhookNotifier("generic", s.GENERIC_WEBHOOK_URL))
            logger.info("已启用通用 Webhook 通知")

    # ------------------------------------------------------------------
    # 运行结果通知
    # ------------------------------------------------------------------

    def notify(self, result: RunResult) -> None:
        """格式化并发送运行结果通知到所有已配置的渠道"""
        if not self.notifiers:
            logger.debug("未配置任何通知渠道，跳过")
            return

        if result.success and not self.settings.NOTIFY_ON_SUCCESS:
            return
        if not result.success and not self.settings.NOTIFY_ON_FAILURE:
            return

        subject = self._format_subject(result)
        body = self._format_body(result)
        attachments = self._collect_attachments(result) if self.settings.NOTIFY_ATTACH_REPORTS else []

        for notifier in self.notifiers:
            try:
                notifier.send(subject, body, attachments)
            except Exception as e:
                logger.warning(f"通知发送失败 ({type(notifier).__name__}): {e}")

    # ------------------------------------------------------------------
    # 错误告警通知
    # ------------------------------------------------------------------

    def notify_error(self, template_name: str, **kwargs) -> None:
        """
        发送错误告警通知。

        使用 configs/notification_templates/ 下的错误模板文件渲染消息并发送。
        仅在 on_failure 为 True 时发送。模板或渠道不存在时静默跳过。

        参数:
            template_name: 模板名称（如 'error_mineru'、'error_llm'、'error_network'、'error_generic'）
            **kwargs: 模板变量
        """
        if not self.notifiers:
            return
        if not self.settings.NOTIFY_ON_FAILURE:
            return

        if "timestamp" not in kwargs:
            kwargs["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        template = _load_template(template_name)
        if template:
            body = _render_template(template, **kwargs)
        else:
            body = f"## ArXiv Daily Researcher\n\n"
            body += f"<font color=\"warning\">**错误告警**</font> | {kwargs.get('timestamp', '')}\n\n"
            for k, v in kwargs.items():
                if k != "timestamp":
                    body += f"> {k}: {v}\n"

        subject = f"ArXiv Daily Researcher - ERROR ({kwargs.get('timestamp', '')})"

        for notifier in self.notifiers:
            try:
                notifier.send(subject, body)
            except Exception as e:
                logger.warning(f"错误告警发送失败 ({type(notifier).__name__}): {e}")

    # ------------------------------------------------------------------
    # 格式化辅助方法
    # ------------------------------------------------------------------

    def _format_subject(self, result: RunResult) -> str:
        status = "SUCCESS" if result.success else "FAILED"
        return f"ArXiv Daily Researcher - {status} ({result.run_timestamp})"

    def _format_body(self, result: RunResult) -> str:
        """使用模板格式化运行结果通知正文，模板不存在时降级为纯文本"""
        template_name = "success" if result.success else "failure"
        template = _load_template(template_name)

        # 构建各数据源统计文本
        source_lines = []
        for source in sorted(result.papers_by_source.keys()):
            fetched = result.papers_by_source.get(source, 0)
            qualified = result.qualified_by_source.get(source, 0)
            analyzed = result.analyzed_by_source.get(source, 0)
            source_lines.append(
                f"> `{source.upper()}` 抓取 **{fetched}** | 及格 **{qualified}** | 分析 **{analyzed}**"
            )
        source_summary = "\n".join(source_lines)

        # 构建报告路径文本
        report_lines = []
        if result.report_paths:
            report_lines.append("**报告路径**")
            for source, path in result.report_paths.items():
                report_lines.append(f"> `{source}` {path}")
        report_list = "\n".join(report_lines)

        # 构建 Top-N 论文文本
        top_lines = []
        if result.top_papers:
            top_lines.append(f"**Top {len(result.top_papers)} 论文**")
            for i, p in enumerate(result.top_papers, 1):
                title = p.get('title', '')[:60]
                score = p.get('score', 0)
                src = p.get('source', '').upper()
                tldr = p.get('tldr', '')[:80]
                url = p.get('url', '')
                top_lines.append(f"> **{i}.** `{src}` {title}")
                top_lines.append(f"> <font color=\"comment\">Score: {score:.1f} | {tldr}</font>")
                if url:
                    top_lines.append(f"> [查看原文]({url})")
        top_papers = "\n".join(top_lines)

        if template:
            return _render_template(
                template,
                status="SUCCESS" if result.success else "FAILED",
                timestamp=result.run_timestamp,
                total_fetched=result.total_papers_fetched,
                total_qualified=result.total_qualified,
                total_analyzed=result.total_analyzed,
                source_summary=source_summary,
                report_list=report_list,
                top_papers=top_papers,
                error_message=result.error_message or "无",
            )

        # 模板不存在时降级为纯文本
        return self._format_body_fallback(result)

    def _format_body_fallback(self, result: RunResult) -> str:
        """模板不存在时的兜底纯文本格式（保持向后兼容）"""
        status_icon = "OK" if result.success else "ERROR"
        lines = [
            f"Status: {status_icon}",
            f"Time: {result.run_timestamp}",
            "",
        ]

        if result.error_message:
            lines.append(f"Error: {result.error_message}")
            lines.append("")

        lines.append("Papers Summary:")
        for source in sorted(result.papers_by_source.keys()):
            fetched = result.papers_by_source.get(source, 0)
            qualified = result.qualified_by_source.get(source, 0)
            analyzed = result.analyzed_by_source.get(source, 0)
            lines.append(
                f"  [{source.upper()}] Fetched: {fetched} | Qualified: {qualified} | Analyzed: {analyzed}"
            )

        lines.append("")
        lines.append(
            f"Total: Fetched {result.total_papers_fetched} | "
            f"Qualified {result.total_qualified} | "
            f"Analyzed {result.total_analyzed}"
        )

        if result.report_paths:
            lines.append("")
            lines.append("Reports:")
            for source, path in result.report_paths.items():
                lines.append(f"  [{source}] {path}")

        if result.top_papers:
            lines.append("")
            lines.append(f"Top {len(result.top_papers)} Papers:")
            for i, p in enumerate(result.top_papers, 1):
                title = p.get('title', '')[:80]
                score = p.get('score', 0)
                src = p.get('source', '').upper()
                tldr = p.get('tldr', '')[:120]
                url = p.get('url', '')
                lines.append(f"  {i}. [{src}] {title}")
                lines.append(f"     Score: {score:.1f} | {tldr}")
                if url:
                    lines.append(f"     {url}")

        return "\n".join(lines)

    def _collect_attachments(self, result: RunResult) -> List[Path]:
        """收集报告文件作为邮件附件"""
        attachments = []
        for source, path_str in result.report_paths.items():
            path = Path(path_str)
            if path.exists() and path.is_file():
                attachments.append(path)
        return attachments
