import asyncio
import json
import sys
import threading
import time
import unittest
import httpx
from openai import APIStatusError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils import llm_stream
from utils.llm_stream import LLMDeferredError, _consume, call_bounded_stream
from config import settings
from agents.analysis_agent import AnalysisAgent
from modes.daily_research import _deep_analyze_single_paper, PaperStageError


def chunk(content=None, reasoning=None, finish=None, usage=None):
    return NS(choices=[NS(index=0, delta=NS(content=content, reasoning_content=reasoning),
                          finish_reason=finish)], usage=usage)


class Stream:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.closed = False
        self.cancelled = False
    def __aiter__(self):
        return self
    async def __anext__(self):
        try:
            delay, event = next(self.actions)
        except StopIteration:
            raise StopAsyncIteration
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return event
    async def close(self):
        self.closed = True


def client_for(stream):
    async def create(**kwargs):
        return stream
    return NS(chat=NS(completions=NS(create=create)), responses=NS(create=create))


class DeepAnalysisStreamTests(unittest.TestCase):
    def setUp(self):
        llm_stream._failures.clear()

    def test_reasoning_is_progress_but_is_not_returned_as_answer(self):
        stream = Stream([(0, chunk(reasoning="private reasoning")), (.03, chunk(reasoning="more")),
                         (.03, chunk(content='{"summary":"ok"}')), (0, chunk(finish="stop", usage={"total_tokens": 5}))])
        text, usage = asyncio.run(_consume(client_for(stream), "chat", {}, .05, .05))
        self.assertEqual(text, '{"summary":"ok"}')
        self.assertEqual(usage["total_tokens"], 5)
        self.assertTrue(stream.closed)

    def test_empty_keepalive_chunks_do_not_reset_first_progress_deadline(self):
        stream = Stream([(.015, chunk(content=" \n", reasoning=" "))] * 10)
        with self.assertRaisesRegex(LLMDeferredError, "首个有效片段"):
            asyncio.run(_consume(client_for(stream), "chat", {}, .04, .2))
        self.assertTrue(stream.closed)
        self.assertTrue(stream.cancelled)

    def test_idle_stream_is_cancelled_and_closed(self):
        stream = Stream([(0, chunk(reasoning="thinking")), (.2, chunk(content="late"))])
        with self.assertRaisesRegex(LLMDeferredError, "连续无进展"):
            asyncio.run(_consume(client_for(stream), "chat", {}, .1, .03))
        self.assertTrue(stream.closed)
        self.assertTrue(stream.cancelled)

    def test_first_deadline_includes_connecting_and_receiving_headers(self):
        async def create(**kwargs):
            await asyncio.sleep(.2)
        client = NS(chat=NS(completions=NS(create=create)))
        with self.assertRaisesRegex(LLMDeferredError, "首个有效片段"):
            asyncio.run(_consume(client, "chat", {}, .02, .1))

    def test_total_deadline_limits_even_continuous_reasoning_and_closes_client(self):
        stream = Stream([(.01, chunk(reasoning="thinking"))] * 100)
        client = client_for(stream)
        closed = []
        async def close():
            closed.append(True)
        client.close = close
        sync = NS(api_key="test", base_url="https://example.test/v1", organization=None, project=None)
        with patch.object(llm_stream, "AsyncOpenAI", return_value=client), patch.multiple(settings,
                LLM_ANALYSIS_FIRST_TOKEN_TIMEOUT_SECONDS=.1, LLM_ANALYSIS_IDLE_TIMEOUT_SECONDS=.1,
                LLM_ANALYSIS_TOTAL_TIMEOUT_SECONDS=.04), patch.object(llm_stream.llm_request_pool, "_wait_for_slot"):
            with self.assertRaisesRegex(LLMDeferredError, "总耗时"):
                call_bounded_stream(sync, model="test")
        self.assertTrue(stream.closed)
        self.assertTrue(stream.cancelled)
        self.assertEqual(closed, [True])

    def test_incomplete_or_length_limited_output_is_not_accepted(self):
        for actions in ([(0, chunk(content="partial"))], [(0, chunk(content="{}", finish="length"))]):
            stream = Stream(actions)
            with self.assertRaises(LLMDeferredError):
                asyncio.run(_consume(client_for(stream), "chat", {}, .1, .1))
            self.assertTrue(stream.closed)

    def test_responses_stream_keeps_answer_usage_and_completion(self):
        stream = Stream([(0, NS(type="response.reasoning_summary_text.delta", delta="private")),
                         (0, NS(type="response.output_text.delta", delta='{"summary":"ok"}')),
                         (0, NS(type="response.completed", response=NS(usage={"total_tokens": 8})))])
        text, usage = asyncio.run(_consume(client_for(stream), "responses", {}, .1, .1))
        self.assertEqual(text, '{"summary":"ok"}')
        self.assertEqual(usage["total_tokens"], 8)

    def test_three_stalls_trigger_short_provider_cooldown(self):
        key = ("test", "model")
        for _ in range(3):
            llm_stream._circuit_record(key, True)
        with self.assertRaisesRegex(LLMDeferredError, "冷却"):
            llm_stream._circuit_check(key)
        llm_stream._circuit_record(key, False)
        llm_stream._circuit_check(key)

    def test_unsupported_route_is_preserved_for_endpoint_fallback(self):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        error = APIStatusError("unsupported endpoint", response=httpx.Response(501, request=request), body=None)
        async def run(*args): raise error
        client = NS(base_url="https://example.test/v1")
        with patch.object(llm_stream, "_run", side_effect=run), patch.object(llm_stream.llm_request_pool, "_wait_for_slot"):
            with self.assertRaises(APIStatusError) as caught:
                call_bounded_stream(client, model="test")
            self.assertIs(caught.exception, error)
        agent = AnalysisAgent.__new__(AnalysisAgent)
        with patch("agents.analysis_agent.endpoint_is_known_unsupported", return_value=False), \
                patch("agents.analysis_agent.record_endpoint_capability"), \
                patch("agents.analysis_agent.call_bounded_stream", side_effect=[error, NS(output_text='{"summary":"ok"}', usage=None)]) as call:
            client.responses = NS(create=lambda: None)
            result, _ = agent._call_llm_with_fallback(client, "test", "prompt", None, stream=True)
        self.assertEqual(result, '{"summary":"ok"}')
        self.assertEqual(call.call_args.kwargs["endpoint"], "responses")

    def test_stalled_paper_releases_slot_without_immediate_retries(self):
        class Agent:
            def __init__(self): self.calls = 0
            def _download_and_parse_pdf(self, _): return "body"
            def deep_analyze(self, **kwargs):
                self.calls += 1
                if kwargs["title"] == "Stalled": raise LLMDeferredError("idle timeout")
                return {"summary": "ok"}
        agent = Agent()
        paper = {"paper_id": "test", "title": "Stalled", "abstract": "", "pdf_url": "https://example.test/p.pdf"}
        with patch.object(settings, "RETRY_MAX_ATTEMPTS", 3):
            with self.assertRaisesRegex(PaperStageError, "1 次"):
                _deep_analyze_single_paper(paper, agent)
            self.assertEqual(agent.calls, 1)
            paper["title"] = "Next"
            self.assertEqual(_deep_analyze_single_paper(paper, agent)["analysis"], {"summary": "ok"})

    def test_smart_call_enables_stream_without_inner_application_retry(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.smart_client = NS()
        with patch.object(agent, "_call_llm_with_fallback", side_effect=LLMDeferredError("stall")) as call, \
                patch.object(settings, "TOKEN_TRACKING_ENABLED", False):
            with self.assertRaises(LLMDeferredError): agent._call_smart_llm("prompt")
        self.assertEqual(call.call_count, 1)
        self.assertTrue(call.call_args.kwargs["stream"])

    def test_real_sdk_closes_stalled_http_stream_and_next_paper_succeeds(self):
        disconnected = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if request["model"] == "stall":
                    for _ in range(50):
                        try:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            disconnected.set()
                            return
                        time.sleep(.02)
                else:
                    payload = {"id": "mock", "object": "chat.completion.chunk", "created": 0,
                               "model": "ok", "choices": [{"index": 0,
                               "delta": {"content": '{"summary":"ok"}'}, "finish_reason": "stop"}]}
                    self.wfile.write(("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode())
                    self.wfile.flush()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        sync = NS(api_key="test", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                  organization=None, project=None)
        try:
            with patch.multiple(settings, LLM_ANALYSIS_FIRST_TOKEN_TIMEOUT_SECONDS=.1,
                                LLM_ANALYSIS_IDLE_TIMEOUT_SECONDS=.1, LLM_ANALYSIS_TOTAL_TIMEOUT_SECONDS=1), \
                    patch.object(llm_stream.llm_request_pool, "_wait_for_slot"):
                with self.assertRaises(LLMDeferredError):
                    call_bounded_stream(sync, model="stall", messages=[{"role": "user", "content": "test"}])
                response = call_bounded_stream(sync, model="ok", messages=[{"role": "user", "content": "test"}])
                self.assertEqual(response.choices[0].message.content, '{"summary":"ok"}')
                self.assertTrue(disconnected.wait(1), "Stalled HTTP connection was not closed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
