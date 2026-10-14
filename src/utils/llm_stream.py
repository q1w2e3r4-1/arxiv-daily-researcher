"""Cancelable deep-analysis streams with first-progress, idle and total bounds."""

import asyncio
import logging
import threading
import time
from types import SimpleNamespace

from openai import AsyncOpenAI

from config import settings
from utils.llm_request_pool import llm_request_pool

logger = logging.getLogger(__name__)


class LLMDeferredError(RuntimeError):
    """Release this paper's worker slot; retry through the persistent queue."""


def is_deferred_llm_error(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, LLMDeferredError):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


_failures = {}
_lock = threading.Lock()


async def _close(resource):
    try:
        await asyncio.wait_for(resource.close(), timeout=5)
    except Exception as exc:
        # Preserve the original timeout/failure classification for the queue.
        logger.warning("深度分析连接关闭未正常完成：%s", type(exc).__name__)


def _circuit_check(key):
    with _lock:
        count, until = _failures.get(key, (0, 0))
        if until > time.monotonic():
            raise LLMDeferredError("深度分析服务连续无进展，短暂冷却中；论文保留供下次重试")
        if until:
            _failures.pop(key, None)


def _circuit_record(key, stalled):
    with _lock:
        if not stalled:
            _failures.pop(key, None)
            return
        count, _ = _failures.get(key, (0, 0))
        count += 1
        _failures[key] = (count, time.monotonic() + 60 if count >= 3 else 0)


async def _consume(client, endpoint, kwargs, first, idle):
    started = time.monotonic()
    last_progress = started
    last_log = started
    progressed = False
    answer = []
    answer_chars = reasoning_chars = 0
    usage = None
    finished = False
    stream = None
    try:
        create = client.chat.completions.create if endpoint == "chat" else client.responses.create
        stream = await asyncio.wait_for(create(**kwargs, stream=True), timeout=first)
        iterator = stream.__aiter__()
        while True:
            remaining = (idle if progressed else first) - (time.monotonic() - last_progress)
            if remaining <= 0:
                raise LLMDeferredError("深度分析流式请求连续无有效输出；论文保留供下次重试")
            try:
                chunk = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            text = reasoning = ""
            if endpoint == "chat":
                usage = getattr(chunk, "usage", None) or usage
                for choice in getattr(chunk, "choices", []) or []:
                    if getattr(choice, "index", 0) != 0:
                        continue
                    delta = choice.delta
                    text += getattr(delta, "content", None) or ""
                    reasoning += getattr(delta, "reasoning_content", None) or ""
                    finish = getattr(choice, "finish_reason", None)
                    if finish is not None:
                        if finish != "stop":
                            raise LLMDeferredError(f"深度分析输出未完整结束（{finish}）；论文保留供重试")
                        finished = True
            else:
                kind = getattr(chunk, "type", "")
                if kind == "response.output_text.delta":
                    text = getattr(chunk, "delta", "") or ""
                elif kind in {"response.reasoning_text.delta", "response.reasoning_summary_text.delta"}:
                    reasoning = getattr(chunk, "delta", "") or ""
                elif kind == "response.completed":
                    usage = getattr(chunk.response, "usage", None)
                    finished = True
                elif kind in {"response.failed", "response.incomplete", "error"}:
                    raise LLMDeferredError("深度分析服务返回失败或不完整流；论文保留供重试")
            if text:
                answer.append(text)
                answer_chars += len(text)
            reasoning_chars += len(reasoning)
            if text.strip() or reasoning.strip():
                progressed = True
                last_progress = time.monotonic()
            now = time.monotonic()
            if now - last_log >= 45:
                logger.info("深度分析流式进度：%.0fs，阶段=%s，推理字符=%s，回答字符=%s",
                            now - started, "回答" if answer_chars else "推理", reasoning_chars, answer_chars)
                last_log = now
        if not finished:
            raise LLMDeferredError("深度分析流提前断开，未收到完成标志；论文保留供重试")
        return "".join(answer), usage
    except asyncio.TimeoutError as exc:
        phase = "连续无进展" if progressed else "等待首个有效片段"
        raise LLMDeferredError(f"深度分析{phase}超时；论文保留供下次重试") from exc
    finally:
        if stream is not None:
            await _close(stream)


async def _run(sync_client, endpoint, kwargs):
    first = settings.LLM_ANALYSIS_FIRST_TOKEN_TIMEOUT_SECONDS
    idle = settings.LLM_ANALYSIS_IDLE_TIMEOUT_SECONDS
    total = settings.LLM_ANALYSIS_TOTAL_TIMEOUT_SECONDS
    # No SDK retries: the paper queue owns retry, and cancellations must close
    # the async transport rather than leave a background thread/socket alive.
    client = AsyncOpenAI(
        api_key=sync_client.api_key, base_url=sync_client.base_url,
        organization=sync_client.organization, project=sync_client.project,
        timeout=max(first, idle), max_retries=0,
    )
    try:
        return await asyncio.wait_for(_consume(client, endpoint, kwargs, first, idle), timeout=total)
    except asyncio.TimeoutError as exc:
        raise LLMDeferredError("深度分析超过总耗时上限；论文保留供下次重试") from exc
    finally:
        await _close(client)


def call_bounded_stream(client, *, endpoint="chat", **kwargs):
    """Synchronous agent boundary; network work inside remains cancellable."""
    key = (str(client.base_url), kwargs.get("model"))
    _circuit_check(key)
    llm_request_pool._wait_for_slot()
    _circuit_check(key)
    if endpoint == "chat":
        kwargs["stream_options"] = {"include_usage": True}
        kwargs["max_tokens"] = 32768
    else:
        kwargs["max_output_tokens"] = 32768
    logger.info("深度分析流式请求开始：首片段=%ss，无进展=%ss，总上限=%ss",
                settings.LLM_ANALYSIS_FIRST_TOKEN_TIMEOUT_SECONDS,
                settings.LLM_ANALYSIS_IDLE_TIMEOUT_SECONDS, settings.LLM_ANALYSIS_TOTAL_TIMEOUT_SECONDS)
    try:
        text, usage = asyncio.run(_run(client, endpoint, kwargs))
    except Exception as exc:
        # Network failures also release the slot instead of multiplying retries.
        from openai import APIConnectionError, APIStatusError
        transient = isinstance(exc, APIConnectionError) or (
            isinstance(exc, APIStatusError) and (exc.status_code == 429 or (
                exc.status_code >= 500 and exc.status_code != 501
            ))
        )
        _circuit_record(key, isinstance(exc, LLMDeferredError) or transient)
        if transient:
            raise LLMDeferredError("深度分析连接失败或服务暂不可用；论文保留供下次重试") from exc
        raise
    _circuit_record(key, False)
    if endpoint == "chat":
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)
    return SimpleNamespace(output_text=text, usage=usage)
