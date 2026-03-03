"""
通知代理模块 - 多渠道通知系统

支持的通知渠道：
- Email: SMTP 邮件通知
- 企业微信: Webhook 机器人
- 钉钉: Webhook 机器人（支持签名验证）
- Telegram: Bot API
- Slack: Incoming Webhook
- 通用 Webhook: 自定义 URL
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
        """企业微信机器人"""
        content = f"## {subject}\n\n{body}"
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
                "text": f"## {subject}\n\n{body}"
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

    def notify(self, result: RunResult) -> None:
        """格式化并发送通知到所有已配置的渠道"""
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

    def _format_subject(self, result: RunResult) -> str:
        status = "SUCCESS" if result.success else "FAILED"
        return f"ArXiv Daily Researcher - {status} ({result.run_timestamp})"

    def _format_body(self, result: RunResult) -> str:
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
