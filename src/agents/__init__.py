"""
LLM Agent 模块：包含系统中调用 LLM 的核心 Agent。

各 Agent 职责：
- KeywordAgent：从参考 PDF 中提取关键概念，自动生成搜索关键词（调用 CHEAP_LLM）
- AnalysisAgent：分两阶段对论文进行分析 — 快速筛选和深度分析（调用 CHEAP_LLM + SMART_LLM）
"""

from .keyword_agent import KeywordAgent
from .analysis_agent import AnalysisAgent

__all__ = ["KeywordAgent", "AnalysisAgent"]
