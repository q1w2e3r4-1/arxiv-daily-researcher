"""
多渠道通知模块

支持邮件、企业微信、钉钉、Telegram、Slack 和自定义 Webhook。
"""

from .notifier import NotifierAgent, RunResult

__all__ = ["NotifierAgent", "RunResult"]
