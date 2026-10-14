"""LLM 超时/重试韧性：客户端边界与共享重试策略。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings  # noqa: E402
from utils.config_io import build_config_dict, flatten_config_dict, validate_config_document  # noqa: E402
from utils.llm_resilience import (  # noqa: E402
    build_llm_client,
    is_retryable_llm_error,
    llm_retry,
)

_REQUEST = httpx.Request("POST", "https://relay.test/v1/chat/completions")


def _status_error(error_cls, status_code: int) -> Exception:
    response = httpx.Response(status_code, request=_REQUEST)
    return error_cls("relay error", response=response, body=None)


class LLMErrorClassificationTests(unittest.TestCase):
    def test_fatal_provider_errors_are_not_retryable(self):
        fatal = [
            _status_error(openai.AuthenticationError, 401),
            _status_error(openai.PermissionDeniedError, 403),
            _status_error(openai.NotFoundError, 404),
            _status_error(openai.BadRequestError, 400),
            _status_error(openai.UnprocessableEntityError, 422),
        ]
        for exc in fatal:
            self.assertFalse(is_retryable_llm_error(exc), msg=repr(exc))

    def test_transient_errors_are_retryable(self):
        transient = [
            _status_error(openai.RateLimitError, 429),
            _status_error(openai.InternalServerError, 500),
            _status_error(openai.APIStatusError, 502),
            openai.APITimeoutError(_REQUEST),
            openai.APIConnectionError(request=_REQUEST),
            ValueError("unknown gateway hiccup"),
        ]
        for exc in transient:
            self.assertTrue(is_retryable_llm_error(exc), msg=repr(exc))


class LLMClientBoundsTests(unittest.TestCase):
    def test_build_llm_client_applies_configured_bounds(self):
        with patch("utils.llm_resilience.settings") as fake_settings:
            fake_settings.LLM_TIMEOUT_SECONDS = 12.5
            fake_settings.LLM_SDK_MAX_RETRIES = 2
            client = build_llm_client("sk-test", "https://relay.test/v1")
        self.assertEqual(client.api_key, "sk-test")
        self.assertEqual(float(client.timeout), 12.5)
        self.assertEqual(client.max_retries, 2)


class LLMRetryPolicyTests(unittest.TestCase):
    _WAIT_PATCH = {
        "LLM_RETRY_MAX_ATTEMPTS": 3,
        "LLM_RETRY_MIN_WAIT": 1,
        "LLM_RETRY_MAX_WAIT": 1,
    }

    def test_retry_recovers_from_transient_errors(self):
        calls = {"n": 0}

        with patch.multiple("utils.llm_resilience.settings", **self._WAIT_PATCH):
            @llm_retry()
            def call():
                calls["n"] += 1
                if calls["n"] < 3:
                    raise _status_error(openai.RateLimitError, 429)
                return "ok"

            self.assertEqual(call(), "ok")
        self.assertEqual(calls["n"], 3)

    def test_fatal_errors_fail_fast_without_retry(self):
        calls = {"n": 0}

        with patch.multiple("utils.llm_resilience.settings", **self._WAIT_PATCH):
            @llm_retry()
            def call():
                calls["n"] += 1
                raise _status_error(openai.AuthenticationError, 401)

            with self.assertRaises(openai.AuthenticationError):
                call()
        self.assertEqual(calls["n"], 1)

    def test_exhausted_retries_reraise_original_error(self):
        with patch.multiple("utils.llm_resilience.settings", **self._WAIT_PATCH):
            @llm_retry()
            def call():
                raise openai.APITimeoutError(_REQUEST)

            with self.assertRaises(openai.APITimeoutError):
                call()


class LLMConfigRoundTripTests(unittest.TestCase):
    def test_settings_load_llm_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                """
                {
                  llm: {
                    timeout_seconds: 240.5,
                    sdk_max_retries: 0,
                    retry_max_attempts: 4,
                    retry_min_wait: 8,
                    retry_max_wait: 90,
                    analysis_first_token_timeout_seconds: 90,
                    analysis_idle_timeout_seconds: 45,
                    analysis_total_timeout_seconds: 600,
                    analysis_input_token_budget: 65536
                  }
                }
                """,
                encoding="utf-8",
            )
            settings = Settings()
            settings.load_from_search_config(config_path)
            self.assertEqual(settings.LLM_TIMEOUT_SECONDS, 240.5)
            self.assertEqual(settings.LLM_SDK_MAX_RETRIES, 0)
            self.assertEqual(settings.LLM_RETRY_MAX_ATTEMPTS, 4)
            self.assertEqual(settings.LLM_RETRY_MIN_WAIT, 8)
            self.assertEqual(settings.LLM_RETRY_MAX_WAIT, 90)
            self.assertEqual(settings.LLM_ANALYSIS_FIRST_TOKEN_TIMEOUT_SECONDS, 90)
            self.assertEqual(settings.LLM_ANALYSIS_IDLE_TIMEOUT_SECONDS, 45)
            self.assertEqual(settings.LLM_ANALYSIS_TOTAL_TIMEOUT_SECONDS, 600)
            self.assertEqual(settings.LLM_ANALYSIS_INPUT_TOKEN_BUDGET, 65536)

    def test_stream_limits_reject_zero_nonfinite_and_boolean_values(self):
        for value in (0, -1, float("nan"), float("inf"), True, "120"):
            with self.assertRaises(ValueError):
                validate_config_document({"llm": {"analysis_idle_timeout_seconds": value}})

    def test_defaults_when_llm_section_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            settings = Settings()
            settings.load_from_search_config(config_path)
            self.assertEqual(settings.LLM_TIMEOUT_SECONDS, 300.0)
            self.assertEqual(settings.LLM_SDK_MAX_RETRIES, 1)
            self.assertEqual(settings.LLM_RETRY_MAX_ATTEMPTS, 5)
            self.assertEqual(settings.LLM_RETRY_MIN_WAIT, 5)
            self.assertEqual(settings.LLM_RETRY_MAX_WAIT, 120)

    def test_config_io_round_trips_llm_section(self):
        config = build_config_dict(
            llm_timeout_seconds=210.0,
            llm_sdk_max_retries=2,
            llm_retry_max_attempts=6,
            llm_retry_min_wait=4,
            llm_retry_max_wait=75,
        )
        self.assertEqual(
            config["llm"],
            {
                "timeout_seconds": 210.0,
                "sdk_max_retries": 2,
                "retry_max_attempts": 6,
                "retry_min_wait": 4,
                "retry_max_wait": 75,
                "analysis_first_token_timeout_seconds": 180.0,
                "analysis_idle_timeout_seconds": 120.0,
                "analysis_total_timeout_seconds": 1200.0,
                "analysis_input_token_budget": 196608,
            },
        )

        flat = flatten_config_dict({"llm": config["llm"]})
        self.assertEqual(flat["llm_timeout_seconds"], 210.0)
        self.assertEqual(flat["llm_sdk_max_retries"], 2)
        self.assertEqual(flat["llm_retry_max_attempts"], 6)
        self.assertEqual(flat["llm_retry_min_wait"], 4)
        self.assertEqual(flat["llm_retry_max_wait"], 75)


if __name__ == "__main__":
    unittest.main()
