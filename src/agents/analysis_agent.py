import json
import logging
import hashlib
import random
import re
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import fitz  # pymupdf
import requests
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from config import settings
from parsers.mineru_parser import MineruParser
from utils.llm_request_pool import call_chat_completion

logger = logging.getLogger(__name__)


class WeightedScoreResponse(BaseModel):
    total_score: float
    keyword_scores: Dict[str, float]
    author_bonus: float
    expert_authors_found: List[str]
    passing_score: float
    is_qualified: bool
    reasoning: str
    tldr: str
    extracted_keywords: List[str]
    scoring_method: str = "keyword_weighted"
    model_judgments: List[Dict[str, Any]] = Field(default_factory=list)
    successful_model_count: int = 0
    fallback_model_count: int = 0
    agreement_ratio: float = 0.0
    aggregate_paper_type: str = ""
    preliminary_score: Optional[float] = None
    smart_review_used: bool = False
    smart_review_model: str = ""
    final_model_count: int = 0


class Stage2Response(BaseModel):
    chinese_title: Optional[str] = None
    summary: Optional[str] = None
    innovations: Optional[List[str]] = None
    methodology: Optional[str] = None
    key_results: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    strengths: Optional[List[str]] = None
    limitations: Optional[List[str]] = None
    relevance_to_keywords: Optional[str] = None
    future_work: Optional[str] = None
    custom_answers: Optional[Dict[str, str]] = None


class CommitteeCallError(RuntimeError):
    def __init__(
        self,
        message: str,
        attempt_count: int,
        retry_events: List[Dict[str, Any]],
        request_latency_seconds: float,
    ):
        super().__init__(message)
        self.attempt_count = attempt_count
        self.retry_count = max(0, attempt_count - 1)
        self.retry_events = retry_events
        self.request_latency_seconds = request_latency_seconds


class AnalysisAgent:
    def __init__(self):
        self.cheap_client = OpenAI(
            api_key=settings.CHEAP_LLM.api_key, base_url=settings.CHEAP_LLM.base_url
        )
        self.smart_client = OpenAI(
            api_key=settings.SMART_LLM.api_key, base_url=settings.SMART_LLM.base_url
        )

        self.mineru_parser = MineruParser()
        self.basic_template = settings.load_report_template("basic_report_template.json")
        self.deep_template = settings.load_report_template("deep_analysis_template.json")
        self.mlsys_prompt_template = settings.load_report_template("mlsys_screening_prompt.json")

        self.committee_run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.committee_artifact_dir = (
            settings.DATA_DIR / "scoring_artifacts" / "mlsys_multi_model" / self.committee_run_id
        )
        self.committee_failures = {model: 0 for model in settings.MLSYS_COMMITTEE_MODELS}
        self.committee_failures_lock = threading.Lock()
        self.committee_artifact_lock = threading.Lock()

        if settings.MLSYS_EXPORT_ARTIFACTS:
            self.committee_artifact_dir.mkdir(parents=True, exist_ok=True)
            meta_path = self.committee_artifact_dir / "run_meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "run_id": self.committee_run_id,
                        "scoring_method": "mlsys_multi_model",
                        "committee_models": settings.MLSYS_COMMITTEE_MODELS,
                        "smart_review_enabled": settings.MLSYS_SMART_REVIEW_ENABLED,
                        "smart_review_model": settings.SMART_LLM.model_name,
                        "smart_review_min_score": settings.MLSYS_SMART_REVIEW_MIN_SCORE,
                        "smart_review_max_score": settings.MLSYS_SMART_REVIEW_MAX_SCORE,
                        "passing_score": settings.MLSYS_PASSING_SCORE,
                        "fallback_score": settings.MLSYS_FALLBACK_SCORE,
                        "circuit_breaker_threshold": settings.MLSYS_CIRCUIT_BREAKER_THRESHOLD,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _call_cheap_llm(self, prompt: str) -> str:
        estimated_prompt_tokens = len(prompt) // 4

        @retry(
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_call():
            try:
                resp, _ = call_chat_completion(
                    client=self.cheap_client,
                    model_name=settings.CHEAP_LLM.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    operation_label="keyword_weighted_scoring",
                    temperature=settings.CHEAP_LLM.temperature,
                    response_format={"type": "json_object"},
                )
            except Exception:
                if settings.TOKEN_TRACKING_ENABLED:
                    from utils.token_counter import token_counter

                    token_counter.add(settings.CHEAP_LLM.model_name, estimated_prompt_tokens, 0)
                raise
            if settings.TOKEN_TRACKING_ENABLED and resp.usage:
                from utils.token_counter import token_counter

                token_counter.add(
                    settings.CHEAP_LLM.model_name,
                    resp.usage.prompt_tokens,
                    resp.usage.completion_tokens,
                )
            return resp.choices[0].message.content

        return _do_call()

    def _call_cheap_llm_plain(self, prompt: str, model_name: Optional[str] = None) -> str:
        selected_model = model_name or settings.CHEAP_LLM.model_name
        estimated_prompt_tokens = len(prompt) // 4

        @retry(
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_call():
            try:
                resp, _ = call_chat_completion(
                    client=self.cheap_client,
                    model_name=selected_model,
                    messages=[{"role": "user", "content": prompt}],
                    operation_label="cheap_plain_text",
                    temperature=0.3,
                )
            except Exception:
                if settings.TOKEN_TRACKING_ENABLED:
                    from utils.token_counter import token_counter

                    token_counter.add(selected_model, estimated_prompt_tokens, 0)
                raise
            if settings.TOKEN_TRACKING_ENABLED and resp.usage:
                from utils.token_counter import token_counter

                token_counter.add(
                    selected_model,
                    resp.usage.prompt_tokens,
                    resp.usage.completion_tokens,
                )
            return resp.choices[0].message.content.strip()

        return _do_call()

    def _call_smart_llm(self, prompt: str) -> str:
        estimated_prompt_tokens = len(prompt) // 4

        @retry(
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_call():
            try:
                resp, _ = call_chat_completion(
                    client=self.smart_client,
                    model_name=settings.SMART_LLM.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    operation_label="deep_analysis",
                    temperature=settings.SMART_LLM.temperature,
                    response_format={"type": "json_object"},
                )
            except Exception:
                if settings.TOKEN_TRACKING_ENABLED:
                    from utils.token_counter import token_counter

                    token_counter.add(settings.SMART_LLM.model_name, estimated_prompt_tokens, 0)
                raise
            if settings.TOKEN_TRACKING_ENABLED and resp.usage:
                from utils.token_counter import token_counter

                token_counter.add(
                    settings.SMART_LLM.model_name,
                    resp.usage.prompt_tokens,
                    resp.usage.completion_tokens,
                )
            return resp.choices[0].message.content

        return _do_call()

    def _download_pdf_bytes(self, pdf_url: str) -> bytes:
        @retry(
            stop=stop_after_attempt(settings.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(min=settings.RETRY_MIN_WAIT, max=settings.RETRY_MAX_WAIT),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_download():
            headers = {
                "User-Agent": "ArxivDailyResearcher/2.0 (https://github.com/yzr278892/arxiv-daily-researcher; yzr278892@gmail.com)"
            }
            resp = requests.get(pdf_url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.content

        return _do_download()

    def _clean_json_string(self, json_str: str) -> str:
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        json_str = json_str.strip()

        def fix_escapes_in_match(match):
            content = match.group(1)
            result = ""
            i = 0
            while i < len(content):
                if content[i] == "\\":
                    if i + 1 < len(content):
                        next_char = content[i + 1]
                        if next_char in ['"', "\\", "/", "b", "f", "n", "r", "t"]:
                            result += content[i : i + 2]
                            i += 2
                        elif next_char == "u" and i + 5 < len(content):
                            result += content[i : i + 6]
                            i += 6
                        else:
                            result += "\\\\"
                            i += 1
                    else:
                        result += "\\\\"
                        i += 1
                else:
                    result += content[i]
                    i += 1
            return f'"{result}"'

        return re.sub(r'"((?:[^"\\]|\\.)*)"', fix_escapes_in_match, json_str)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _extract_usage(self, resp: Any) -> Dict[str, int]:
        usage = getattr(resp, "usage", None)
        if not usage:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }

    def _parse_model_json(self, raw_text: str) -> Dict[str, Any]:
        text = self._clean_json_string(raw_text or "").strip()
        if not text:
            raise json.JSONDecodeError("empty response", raw_text or "", 0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
        if fenced:
            return json.loads(fenced.group(1).strip())
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise json.JSONDecodeError("no json object found", raw_text or "", 0)

    def _build_mlsys_prompts(
        self, title: str, abstract: str, source: str, categories: Optional[List[str]] = None
    ) -> tuple[str, str]:
        template = self.mlsys_prompt_template or {}
        prompts = template.get("prompts", {})
        system_prompt = prompts.get(
            "system",
            "You are screening research papers for an AI infrastructure researcher. Judge MLSys relevance from the title and abstract only.",
        )
        user_prompt = prompts.get("user_template", "Title: {title}\nAbstract: {abstract}")
        category_text = ", ".join(categories or []) if categories else source or "arXiv"
        replacements = {
            "{title}": title,
            "{abstract}": abstract or "",
            "{source}": source or "arXiv",
            "{categories}": category_text,
        }
        for old, new in replacements.items():
            user_prompt = user_prompt.replace(old, str(new))
        return system_prompt, user_prompt

    def _call_screening_model(
        self,
        client: OpenAI,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        paper_id: str,
        title: str,
        stage_label: str,
    ) -> tuple[str, float, Dict[str, int], int, int, List[Dict[str, Any]]]:
        estimated_prompt_tokens = (len(system_prompt) + len(user_prompt)) // 4
        last_error: Exception | None = None
        retry_events: List[Dict[str, Any]] = []

        for attempt in range(settings.RETRY_MAX_ATTEMPTS):
            started = time.perf_counter()
            try:
                resp, _ = call_chat_completion(
                    client=client,
                    model_name=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    operation_label=stage_label,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                latency = time.perf_counter() - started
                usage = self._extract_usage(resp)
                content = resp.choices[0].message.content or ""

                if settings.TOKEN_TRACKING_ENABLED:
                    from utils.token_counter import token_counter

                    if usage["total_tokens"] > 0:
                        token_counter.add(
                            model_name, usage["prompt_tokens"], usage["completion_tokens"]
                        )
                    else:
                        token_counter.add(model_name, estimated_prompt_tokens, len(content) // 4)

                return content, latency, usage, attempt, attempt + 1, retry_events
            except Exception as exc:
                last_error = exc
                latency = time.perf_counter() - started
                error_text = str(exc)
                if settings.TOKEN_TRACKING_ENABLED:
                    from utils.token_counter import token_counter

                    token_counter.add(model_name, estimated_prompt_tokens, 0)
                if attempt == settings.RETRY_MAX_ATTEMPTS - 1:
                    logger.warning(
                        f"委员会模型最终失败 [{stage_label}] [{model_name}] [{paper_id}] [{title[:80]}] | "
                        f"attempt={attempt + 1}/{settings.RETRY_MAX_ATTEMPTS} | error={error_text}"
                    )
                    raise CommitteeCallError(
                        message=error_text,
                        attempt_count=attempt + 1,
                        retry_events=retry_events,
                        request_latency_seconds=round(latency, 4),
                    )
                wait_seconds = min(
                    settings.RETRY_MAX_WAIT,
                    max(settings.RETRY_MIN_WAIT, 2**attempt) + random.random(),
                )
                retry_event = {
                    "attempt": attempt + 1,
                    "error": error_text,
                    "request_latency_seconds": round(latency, 4),
                    "backoff_seconds": round(wait_seconds, 4),
                }
                retry_events.append(retry_event)
                logger.warning(
                    f"委员会模型重试 [{stage_label}] [{model_name}] [{paper_id}] [{title[:80]}] | "
                    f"attempt={attempt + 1}/{settings.RETRY_MAX_ATTEMPTS} | "
                    f"request_latency={latency:.2f}s | backoff={wait_seconds:.2f}s | error={error_text}"
                )
                time.sleep(wait_seconds)

        raise RuntimeError(str(last_error) if last_error else "unknown committee llm error")

    def _call_committee_model(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        paper_id: str,
        title: str,
    ) -> tuple[str, float, Dict[str, int], int, int, List[Dict[str, Any]]]:
        return self._call_screening_model(
            client=self.cheap_client,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            paper_id=paper_id,
            title=title,
            stage_label="cheap_committee",
        )

    def _append_jsonl(self, path: Path, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _persist_committee_artifacts(
        self,
        raw_rows: List[Dict[str, Any]],
        judgment_rows: List[Dict[str, Any]],
        summary_row: Dict[str, Any],
    ) -> None:
        if not settings.MLSYS_EXPORT_ARTIFACTS:
            return
        with self.committee_artifact_lock:
            self._append_jsonl(self.committee_artifact_dir / "raw_responses.jsonl", raw_rows)
            self._append_jsonl(self.committee_artifact_dir / "judgments.jsonl", judgment_rows)
            self._append_jsonl(
                self.committee_artifact_dir / "fallbacks.jsonl",
                [row for row in judgment_rows if row.get("fallback_due_to_error")],
            )
            self._append_jsonl(self.committee_artifact_dir / "paper_scores.jsonl", [summary_row])

    def _make_committee_judgment(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        source: str,
        categories: Optional[List[str]],
        model_name: str,
        stage: str,
        paper_type: str,
        base_score: float,
        preference_bonus: int,
        final_score: float,
        passed: bool,
        reason: str,
        latency: float,
        usage: Dict[str, int],
        retry_count: int,
        attempt_count: int,
        retry_events: List[Dict[str, Any]],
        fallback_due_to_error: bool,
        fallback_error: str,
    ) -> Dict[str, Any]:
        return {
            "paper_id": paper_id,
            "title": title,
            "abstract": abstract or "",
            "source": source,
            "categories": categories or [],
            "model": model_name,
            "stage": stage,
            "paper_type": paper_type,
            "base_score": base_score,
            "preference_bonus": preference_bonus,
            "final_score": final_score,
            "pass": passed,
            "reason": reason,
            "latency_seconds": round(latency, 4),
            "retry_count": retry_count,
            "attempt_count": attempt_count,
            "retry_events": retry_events,
            "fallback_due_to_error": fallback_due_to_error,
            "fallback_error": fallback_error,
            **usage,
        }

    def _make_fallback_committee_judgment(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        source: str,
        categories: Optional[List[str]],
        model_name: str,
        stage: str,
        error: str,
        latency: float,
        usage: Dict[str, int],
        retry_count: int,
        attempt_count: int,
        retry_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback_score = float(settings.MLSYS_FALLBACK_SCORE)
        return self._make_committee_judgment(
            paper_id=paper_id,
            title=title,
            abstract=abstract,
            source=source,
            categories=categories,
            model_name=model_name,
            stage=stage,
            paper_type="fallback_error",
            base_score=fallback_score,
            preference_bonus=0,
            final_score=fallback_score,
            passed=False,
            reason=f"Fallback score after repeated API failure: {error}",
            latency=latency,
            usage=usage,
            retry_count=retry_count,
            attempt_count=attempt_count,
            retry_events=retry_events,
            fallback_due_to_error=True,
            fallback_error=error,
        )

    def _summarize_committee_reasons(
        self, judgments: List[Dict[str, Any]], is_qualified: bool, total_score: float
    ) -> str:
        successful_rows = [row for row in judgments if not row.get("fallback_due_to_error")]
        fallback_count = len(judgments) - len(successful_rows)
        pass_votes = sum(1 for row in successful_rows if row.get("pass"))
        outcome = "qualified" if is_qualified else "not qualified"
        cheap_count = sum(1 for row in judgments if row.get("stage") == "cheap_committee")
        smart_used = any(row.get("stage") == "smart_review" for row in judgments)

        parts = [
            (
                f"Committee result: first averaged {cheap_count} cheap-model final scores; "
                f"borderline papers may add one SMART_LLM review; pass threshold is "
                f"{float(settings.MLSYS_PASSING_SCORE):.1f}; fallback rows contribute "
                f"{float(settings.MLSYS_FALLBACK_SCORE):.1f}."
            ),
            f"Aggregate score: {total_score:.2f}. Smart review used: {'yes' if smart_used else 'no'}. Ensemble decision: {outcome}.",
            (
                f"Diagnostic only: {pass_votes}/{len(successful_rows)} successful non-fallback "
                f"model judgments individually passed; {fallback_count} fallback(s)."
            ),
        ]

        paper_types = [row.get("paper_type", "") for row in successful_rows if row.get("paper_type")]
        if paper_types:
            parts.append(f"Dominant paper type: {Counter(paper_types).most_common(1)[0][0]}.")

        reason_bits = []
        for row in judgments:
            reason = " ".join((row.get("reason") or "").split())
            if reason:
                reason_bits.append(f"{row['model']}: {reason}")
            if len(reason_bits) >= 3:
                break
        if reason_bits:
            parts.append(" ".join(reason_bits))

        return " ".join(parts)

    def score_paper(
        self,
        title: str,
        authors: str,
        abstract: str,
        keywords_dict: Optional[Dict[str, float]] = None,
        paper_id: str = "",
        source: str = "",
        categories: Optional[List[str]] = None,
    ) -> WeightedScoreResponse:
        if settings.is_committee_scoring_enabled():
            return self.score_paper_with_committee(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                source=source,
                categories=categories,
            )
        return self.score_paper_with_keywords(
            title=title,
            authors=authors,
            abstract=abstract,
            keywords_dict=keywords_dict or {},
        )

    def score_paper_with_keywords(
        self, title: str, authors: str, abstract: str, keywords_dict: Dict[str, float]
    ) -> WeightedScoreResponse:
        total_weight = sum(keywords_dict.values())
        passing_score = settings.calculate_passing_score(total_weight)

        keywords_list = "\n".join(
            [f"  - {kw} (权重: {weight:.1f})" for kw, weight in keywords_dict.items()]
        )
        expert_authors_str = ", ".join(settings.EXPERT_AUTHORS) if settings.EXPERT_AUTHORS else "无"

        prompt = f"""你是一名学术论文评审专家。请基于以下关键词对论文进行相关性评分，并提取论文信息。

研究背景:
{settings.RESEARCH_CONTEXT if settings.RESEARCH_CONTEXT else "通用学术研究"}

评分关键词及权重:
{keywords_list}

论文信息:
标题: {title}
作者: {authors}
摘要: {abstract}

评分任务:
1. 理解论文的研究内容和主题
2. 对每个关键词评估相关度（0-10分）:
   - 0分: 完全无关
   - 5分: 有一定关联
   - 10分: 高度相关，核心内容
3. 计算加权总分: Σ(关键词相关度 × 关键词权重)
4. 检查作者列表是否包含以下专家: {expert_authors_str}
   - 如果包含，每位专家加 {settings.AUTHOR_BONUS_POINTS} 分
5. 用一句话总结论文研究的问题和结果（TLDR）
6. 从标题和摘要中提取5-8个核心关键词（英文）

评分标准:
- 关键词总权重: {total_weight:.1f}
- 动态及格分: {passing_score:.1f}
- 每个关键词最高相关度: {settings.MAX_SCORE_PER_KEYWORD} 分

输出格式: JSON对象，包含以下字段:
{{
  "keyword_scores": {{"关键词1": 8.0, "关键词2": 5.0, ...}},
  "expert_authors_found": ["Author1", "Author2"],
  "reasoning": "详细的评分理由和分析",
  "tldr": "一句话总结论文研究的核心问题和主要结果",
  "extracted_keywords": ["keyword1", "keyword2", "keyword3", ...]
}}

要求:
- keyword_scores 必须包含所有给定的关键词
- 每个关键词的评分范围: 0-{settings.MAX_SCORE_PER_KEYWORD}
- reasoning 应简明扼要地说明论文与关键词的相关性
- tldr 应该是一句完整的话，包含研究问题和主要结果
- extracted_keywords 应提取5-8个最能代表论文内容的关键词或短语
"""

        try:
            content = self._call_cheap_llm(prompt)
            content = self._clean_json_string(content)
            data = json.loads(content)

            keyword_scores = data.get("keyword_scores", {})
            expert_authors_found = data.get("expert_authors_found", [])
            reasoning = data.get("reasoning", "无详细理由")
            tldr = data.get("tldr", "无摘要")
            extracted_keywords = data.get("extracted_keywords", [])

            weighted_score = sum(
                keyword_scores.get(kw, 0) * weight for kw, weight in keywords_dict.items()
            )

            author_bonus = 0.0
            if settings.ENABLE_AUTHOR_BONUS and expert_authors_found:
                author_bonus = len(expert_authors_found) * settings.AUTHOR_BONUS_POINTS

            total_score = weighted_score + author_bonus
            is_qualified = total_score >= passing_score

            logger.info(
                f"论文评分完成 [{title[:50]}]: 总分={total_score:.1f}, 及格分={passing_score:.1f}, {'✅及格' if is_qualified else '❌未及格'}"
            )

            return WeightedScoreResponse(
                total_score=total_score,
                keyword_scores=keyword_scores,
                author_bonus=author_bonus,
                expert_authors_found=expert_authors_found,
                passing_score=passing_score,
                is_qualified=is_qualified,
                reasoning=reasoning,
                tldr=tldr,
                extracted_keywords=extracted_keywords,
                scoring_method="keyword_weighted",
            )

        except Exception as e:
            logger.error(f"论文评分失败 [{title[:50]}]: {e}")
            import traceback

            traceback.print_exc()

            return WeightedScoreResponse(
                total_score=0.0,
                keyword_scores={kw: 0.0 for kw in keywords_dict.keys()},
                author_bonus=0.0,
                expert_authors_found=[],
                passing_score=passing_score,
                is_qualified=False,
                reasoning=f"评分失败: {str(e)}",
                tldr="评分失败，无法生成摘要",
                extracted_keywords=[],
                scoring_method="keyword_weighted",
            )

    def score_paper_with_committee(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        source: str,
        categories: Optional[List[str]] = None,
    ) -> WeightedScoreResponse:
        system_prompt, user_prompt = self._build_mlsys_prompts(title, abstract, source, categories)
        raw_rows: List[Dict[str, Any]] = []
        judgments: List[Dict[str, Any]] = []
        smart_review_model = settings.SMART_LLM.model_name

        def score_one_model(model_name: str, stage: str, client: OpenAI) -> None:
            latency = 0.0
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            raw_text = ""
            error = ""
            retry_count = 0
            attempt_count = 0
            retry_events: List[Dict[str, Any]] = []

            with self.committee_failures_lock:
                failure_count = self.committee_failures.get(model_name, 0)

            if failure_count >= settings.MLSYS_CIRCUIT_BREAKER_THRESHOLD:
                error = f"circuit_breaker_open_after_{failure_count}_consecutive_failures"
                fallback = self._make_fallback_committee_judgment(
                    paper_id=paper_id,
                    title=title,
                    abstract=abstract,
                    source=source,
                    categories=categories,
                    model_name=model_name,
                    stage=stage,
                    error=error,
                    latency=latency,
                    usage=usage,
                    retry_count=retry_count,
                    attempt_count=attempt_count,
                    retry_events=retry_events,
                )
                raw_rows.append(
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "abstract": abstract or "",
                        "source": source,
                        "categories": categories or [],
                        "model": model_name,
                        "stage": stage,
                        "raw_response": raw_text,
                        "latency_seconds": round(latency, 4),
                        "retry_count": retry_count,
                        "attempt_count": attempt_count,
                        "retry_events": retry_events,
                        "error": error,
                        **usage,
                    }
                )
                judgments.append(fallback)
                return

            try:
                raw_text, latency, usage, retry_count, attempt_count, retry_events = self._call_screening_model(
                    client=client,
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    paper_id=paper_id,
                    title=title,
                    stage_label=stage,
                )
                parsed = self._parse_model_json(raw_text)
                with self.committee_failures_lock:
                    self.committee_failures[model_name] = 0

                base_score = self._safe_int(
                    parsed.get("base_score"), int(settings.MLSYS_FALLBACK_SCORE)
                )
                preference_bonus = self._safe_int(parsed.get("preference_bonus"), 0)
                final_score = float(base_score + preference_bonus)
                passed = final_score >= float(settings.MLSYS_PASSING_SCORE)

                judgments.append(
                    self._make_committee_judgment(
                        paper_id=paper_id,
                        title=title,
                        abstract=abstract,
                        source=source,
                        categories=categories,
                        model_name=model_name,
                        stage=stage,
                        paper_type=parsed.get("paper_type", ""),
                        base_score=base_score,
                        preference_bonus=preference_bonus,
                        final_score=final_score,
                        passed=passed,
                        reason=parsed.get("reason", ""),
                        latency=latency,
                        usage=usage,
                        retry_count=retry_count,
                        attempt_count=attempt_count,
                        retry_events=retry_events,
                        fallback_due_to_error=False,
                        fallback_error="",
                    )
                )
            except Exception as exc:
                error = str(exc)
                if isinstance(exc, CommitteeCallError):
                    latency = exc.request_latency_seconds
                    retry_count = exc.retry_count
                    attempt_count = exc.attempt_count
                    retry_events = exc.retry_events
                with self.committee_failures_lock:
                    self.committee_failures[model_name] = self.committee_failures.get(model_name, 0) + 1
                fallback = self._make_fallback_committee_judgment(
                    paper_id=paper_id,
                    title=title,
                    abstract=abstract,
                    source=source,
                    categories=categories,
                    model_name=model_name,
                    stage=stage,
                    error=error,
                    latency=latency,
                    usage=usage,
                    retry_count=retry_count,
                    attempt_count=attempt_count,
                    retry_events=retry_events,
                )
                judgments.append(fallback)
                logger.warning(f"委员会模型评分失败 [{stage}] [{model_name}] [{title[:50]}]: {error}")

            raw_rows.append(
                {
                    "paper_id": paper_id,
                    "title": title,
                    "abstract": abstract or "",
                    "source": source,
                    "categories": categories or [],
                    "model": model_name,
                    "stage": stage,
                    "raw_response": raw_text,
                    "latency_seconds": round(latency, 4),
                    "retry_count": retry_count,
                    "attempt_count": attempt_count,
                    "retry_events": retry_events,
                    "error": error,
                    **usage,
                }
            )

        for model_name in settings.MLSYS_COMMITTEE_MODELS:
            score_one_model(model_name=model_name, stage="cheap_committee", client=self.cheap_client)

        cheap_judgments = [row for row in judgments if row.get("stage") == "cheap_committee"]
        preliminary_score = (
            sum(float(row.get("final_score", 0)) for row in cheap_judgments) / len(cheap_judgments)
            if cheap_judgments
            else float(settings.MLSYS_FALLBACK_SCORE)
        )

        smart_review_used = (
            settings.MLSYS_SMART_REVIEW_ENABLED
            and settings.MLSYS_SMART_REVIEW_MIN_SCORE <= preliminary_score <= settings.MLSYS_SMART_REVIEW_MAX_SCORE
        )
        if smart_review_used:
            logger.info(
                f"SMART_LLM 复核已触发 [{paper_id}] [{title[:80]}] | 初筛均分={preliminary_score:.2f} | 区间=[{settings.MLSYS_SMART_REVIEW_MIN_SCORE:.1f}, {settings.MLSYS_SMART_REVIEW_MAX_SCORE:.1f}] | 复核模型={smart_review_model}"
            )
            score_one_model(model_name=smart_review_model, stage="smart_review", client=self.smart_client)

        successful_rows = [row for row in judgments if not row.get("fallback_due_to_error")]
        successful_model_count = len(successful_rows)
        fallback_model_count = len(judgments) - successful_model_count
        pass_votes = sum(1 for row in successful_rows if row.get("pass"))
        fail_votes = successful_model_count - pass_votes
        total_score = (
            sum(float(row.get("final_score", 0)) for row in judgments) / len(judgments)
            if judgments
            else float(settings.MLSYS_FALLBACK_SCORE)
        )
        passing_score = float(settings.MLSYS_PASSING_SCORE)
        is_qualified = total_score >= passing_score

        agreement_ratio = (
            max(pass_votes, fail_votes) / successful_model_count if successful_model_count else 0.0
        )
        paper_types = [row.get("paper_type", "") for row in successful_rows if row.get("paper_type")]
        aggregate_paper_type = Counter(paper_types).most_common(1)[0][0] if paper_types else ""
        reasoning = self._summarize_committee_reasons(judgments, is_qualified, total_score)

        summary_row = {
            "paper_id": paper_id,
            "title": title,
            "source": source,
            "categories": categories or [],
            "scoring_method": "mlsys_multi_model",
            "preliminary_score": round(preliminary_score, 4),
            "smart_review_used": smart_review_used,
            "smart_review_model": smart_review_model if smart_review_used else "",
            "final_model_count": len(judgments),
            "total_score": round(total_score, 4),
            "passing_score": passing_score,
            "is_qualified": is_qualified,
            "successful_model_count": successful_model_count,
            "fallback_model_count": fallback_model_count,
            "agreement_ratio": round(agreement_ratio, 4),
            "aggregate_paper_type": aggregate_paper_type,
            "models": [row.get("model") for row in judgments],
            "passes": [bool(row.get("pass")) for row in judgments],
        }
        self._persist_committee_artifacts(raw_rows, judgments, summary_row)

        score_breakdown = "; ".join(
            (
                f"{row.get('model', '')}="
                f"{float(row.get('final_score', 0)):.1f}"
                f" ({'fallback' if row.get('fallback_due_to_error') else 'ok'})"
            )
            for row in judgments
        )
        logger.info(
            f"委员会评分完成 [{title}]:\n明细=[{score_breakdown}] | 初筛均分={preliminary_score:.2f} | 最终均分={total_score:.2f} | 及格线={passing_score:.1f} | {'✅及格' if is_qualified else '❌未及格'}"
        )

        return WeightedScoreResponse(
            total_score=total_score,
            keyword_scores={},
            author_bonus=0.0,
            expert_authors_found=[],
            passing_score=passing_score,
            is_qualified=is_qualified,
            reasoning=reasoning,
            tldr="",
            extracted_keywords=[],
            scoring_method="mlsys_multi_model",
            model_judgments=judgments,
            successful_model_count=successful_model_count,
            fallback_model_count=fallback_model_count,
            agreement_ratio=agreement_ratio,
            aggregate_paper_type=aggregate_paper_type,
            preliminary_score=preliminary_score,
            smart_review_used=smart_review_used,
            smart_review_model=smart_review_model if smart_review_used else "",
            final_model_count=len(judgments),
        )

    def _get_translation_model_name(self) -> str:
        # CHEAP_LLM 可能承载多个委员会模型；翻译是单模型辅助任务，优先选择 qwen3.5-27b，
        # 因为它通常是这里最快的选项。若未配置该模型，则回退到列表中的第一个可用模型。
        cheap_models = settings._split_model_names(settings.CHEAP_LLM.model_name)
        committee_models = list(settings.MLSYS_COMMITTEE_MODELS or [])
        candidates = cheap_models or committee_models or [settings.CHEAP_LLM.model_name]
        for model_name in candidates:
            if model_name == "qwen3.5-27b":
                return model_name
        return candidates[0]

    def translate_abstract(self, abstract: str) -> str:
        prompt = f"""请将以下学术论文摘要翻译为中文。要求：
1. 保持学术术语的准确性
2. 语句通顺流畅
3. 保留专业名词的英文（可在首次出现时标注）

英文摘要：
{abstract}

请直接输出中文翻译，不要添加任何说明或标记。"""

        model_name = self._get_translation_model_name()
        try:
            translation = self._call_cheap_llm_plain(prompt, model_name=model_name)
            logger.info(f"摘要翻译完成 [{model_name}] [{abstract[:30]}...]")
            return translation
        except Exception as e:
            logger.error(f"摘要翻译失败 [{model_name}]: {e}")
            return ""

    def deep_analyze(
        self, title: str, pdf_url: str, abstract: str, fallback_to_abstract: bool = True
    ) -> Optional[Dict[str, Any]]:
        pdf_text = self._download_and_parse_pdf(pdf_url)

        if not pdf_text:
            if fallback_to_abstract:
                logger.warning(f"PDF解析失败 [{title[:50]}]，使用摘要作为降级方案")
                pdf_text = abstract
            else:
                logger.error(f"PDF解析失败 [{title[:50]}]，且未启用降级方案")
                return None

        modules = self.deep_template.get("modules", [])
        prompts_config = self.deep_template.get("prompts", {})
        enabled_modules = [m for m in modules if m.get("enabled", True)]

        field_prompts_lines = []
        output_fields = []

        for module in enabled_modules:
            module_id = module.get("id")
            module_prompt = module.get("prompt", "")

            if module_id == "custom_questions":
                questions = module.get("questions", [])
                if questions:
                    field_prompts_lines.append("\n自定义问题:")
                    for i, q in enumerate(questions, 1):
                        field_prompts_lines.append(f"{i}. {q}")
                    output_fields.append(
                        '  "custom_answers": {"问题1": "回答1", "问题2": "回答2", ...}'
                    )
            else:
                field_prompts_lines.append(f"\n{module_id}: {module_prompt}")
                output_fields.append(f'  "{module_id}": "..."')

        fields_str = ",\n".join(output_fields)
        field_prompts_str = "\n".join(field_prompts_lines)

        system_prompt = prompts_config.get("analysis_system", "你是一名学术论文分析专家。")
        analysis_template = prompts_config.get("analysis_template", "")

        if analysis_template:
            prompt = analysis_template.format(
                title=title,
                content=pdf_text[:15000],
                research_context=(
                    settings.RESEARCH_CONTEXT if settings.RESEARCH_CONTEXT else "通用学术研究"
                ),
                field_prompts=field_prompts_str,
            )
        else:
            prompt = f"""论文标题: {title}

论文内容:
{pdf_text[:15000]}

研究背景:
{settings.RESEARCH_CONTEXT if settings.RESEARCH_CONTEXT else "通用学术研究"}

分析要求:
{field_prompts_str}

输出格式（JSON）:
{{
{fields_str}
}}
"""

        prompt += f"\n\n{prompts_config.get('field_output_format', '使用JSON格式输出。')}"

        try:
            content = self._call_smart_llm(prompt)
            content = self._clean_json_string(content)
            result = json.loads(content)
            logger.info(f"深度分析完成 [{title[:50]}]")
            return result
        except Exception as e:
            logger.error(f"深度分析失败 [{title[:50]}]: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _download_and_parse_pdf(self, pdf_url: str) -> Optional[str]:
        if settings.PDF_PARSER_MODE == "mineru":
            text = self._parse_pdf_with_mineru(pdf_url)
            if text:
                return text
            logger.info("降级使用 PyMuPDF 本地解析")

        return self._parse_pdf_with_pymupdf(pdf_url)

    def _parse_pdf_with_mineru(self, pdf_url: str) -> Optional[str]:
        if not self.mineru_parser.is_available():
            if not self.mineru_parser.is_configured():
                logger.warning("MinerU API 未配置（MINERU_API_KEY 为空），使用 PyMuPDF 本地解析")
            return None

        text = self.mineru_parser.parse_pdf(pdf_url)
        if text:
            logger.info(f"MinerU 解析成功，获取 {len(text)} 字符")
        return text

    def _parse_pdf_with_pymupdf(self, pdf_url: str) -> Optional[str]:
        try:
            pdf_bytes = self._download_pdf_bytes(pdf_url)
            temp_pdf = (
                settings.DOWNLOAD_DIR
                / f"temp_{hashlib.md5(pdf_url.encode()).hexdigest()[:16]}_{threading.get_ident()}.pdf"
            )
            with open(temp_pdf, "wb") as f:
                f.write(pdf_bytes)

            try:
                with fitz.open(temp_pdf) as doc:
                    text = ""
                    for i, page in enumerate(doc):
                        if i >= 20:
                            break
                        text += page.get_text()
            finally:
                if temp_pdf.exists():
                    temp_pdf.unlink()

            logger.info(f"PyMuPDF 解析成功，提取 {len(text)} 字符")
            return text
        except Exception as e:
            logger.error(f"PyMuPDF PDF下载/解析失败: {e}")
            return None
