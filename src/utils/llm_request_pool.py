import logging
import math
import threading
import time
from typing import Any, Dict, List, Tuple

from config import settings

logger = logging.getLogger(__name__)

# 由于LLM 请求可能会比较慢，且某些模型的速率限制较低，因此引入一个全局的请求池来控制请求速率，避免过快地发送请求导致错误。
# 至少对于“致远一号”而言，所有的模型请求共享一个速率限制，每分钟10个请求（虽然实操中glm经常超rate, 应该是太多人用这个模型了）
class LLMRequestPool:
    _instance = None
    _cls_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._lock = threading.Lock()
                    obj._next_allowed_at = 0.0
                    cls._instance = obj
        return cls._instance

    def _get_runtime_config(self) -> Tuple[bool, float, float]:
        enabled = bool(settings.LLM_REQUEST_POOL_ENABLED)
        requests_per_minute = float(settings.LLM_REQUESTS_PER_MINUTE)
        slow_wait_seconds = max(0.0, float(settings.LLM_REQUEST_POOL_LOG_SLOW_WAIT_SECONDS))
        return enabled and requests_per_minute > 0, requests_per_minute, slow_wait_seconds

    def reserve_slot(self, operation_label: str, model_name: str) -> Dict[str, Any]:
        enabled, requests_per_minute, slow_wait_seconds = self._get_runtime_config()
        if not enabled:
            return {
                "enabled": False,
                "queued_wait_seconds": 0.0,
                "queue_depth": 0,
                "requests_per_minute": requests_per_minute,
            }

        interval_seconds = 60.0 / requests_per_minute
        now = time.monotonic()
        with self._lock:
            scheduled_at = max(now, self._next_allowed_at)
            wait_seconds = max(0.0, scheduled_at - now)
            queue_depth = int(math.ceil(wait_seconds / interval_seconds)) if wait_seconds > 0 else 0
            self._next_allowed_at = scheduled_at + interval_seconds

        if wait_seconds > 0:
            log_message = (
                f"LLM 请求排队 [{operation_label}] [{model_name}] | wait={wait_seconds:.2f}s | "
                f"queue_depth≈{queue_depth} | rate={requests_per_minute:.1f}/min"
            )
            if wait_seconds >= slow_wait_seconds:
                logger.info(log_message)
            else:
                logger.debug(log_message)
            time.sleep(wait_seconds)
        else:
            logger.debug(
                f"LLM 请求放行 [{operation_label}] [{model_name}] | rate={requests_per_minute:.1f}/min"
            )

        return {
            "enabled": True,
            "queued_wait_seconds": round(wait_seconds, 4),
            "queue_depth": queue_depth,
            "requests_per_minute": requests_per_minute,
        }


llm_request_pool = LLMRequestPool()


def call_chat_completion(
    client: Any,
    model_name: str,
    messages: List[Dict[str, Any]],
    operation_label: str,
    **kwargs: Any,
) -> Tuple[Any, Dict[str, Any]]:
    queue_meta = llm_request_pool.reserve_slot(
        operation_label=operation_label,
        model_name=model_name,
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        **kwargs,
    )
    return response, queue_meta
