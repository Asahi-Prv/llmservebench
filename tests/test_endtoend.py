from __future__ import annotations

import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from llmservebench.bench import CommonConfig, TargetConfig
from llmservebench.client import OpenAICompatClient
from llmservebench.runner import BenchSettings, run_benchmark
from tests.mock_backend import create_test_server


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.port = create_test_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _settings(self, targets, **overrides):
        common_kwargs = dict(
            parallel_levels=[1, 2],
            max_tokens=32,
            runs=2,
            parallel_runs=1,
            prefill_target_tokens=128,
            warmup=True,
        )
        common_kwargs.update(overrides)
        return BenchSettings(
            mode="compare" if len(targets) > 1 else "single",
            targets=targets,
            common=CommonConfig(**common_kwargs),
        )

    def test_single_mode_produces_metrics(self):
        settings = self._settings(
            [TargetConfig(name="mock", base_url=f"http://127.0.0.1:{self.port}/v1", model="mock-model")]
        )
        result = asyncio.run(run_benchmark(settings))
        self.assertEqual(result["mode"], "single")
        target = result["targets"]["mock"]
        self.assertNotIn("error", target)
        s = target["summary"]
        self.assertGreater(s["ttft_s_median"], 0)
        self.assertGreater(s["gen_tok_per_s_median"], 0)
        self.assertGreater(s["tpot_s_median"], 0)
        self.assertGreater(s["prefill_prompt_tok_per_s_median"], 0)
        self.assertIsNotNone(s["parallel_aggregate_tok_per_s_peak"])
        # usage から正確なトークン数が取れている
        single = target["phases"]["single"]
        self.assertEqual(single["completion_tokens"]["median"], 24.0)

    def test_compare_mode_produces_comparison(self):
        base = f"http://127.0.0.1:{self.port}/v1"
        settings = self._settings(
            [
                TargetConfig(name="a", base_url=base, model="mock-model"),
                TargetConfig(name="b", base_url=base, model="mock-model"),
            ],
            parallel_levels=[1],
            max_tokens=16,
            runs=1,
            parallel_runs=1,
            prefill_target_tokens=64,
            warmup=False,
        )
        result = asyncio.run(run_benchmark(settings))
        self.assertEqual(result["mode"], "compare")
        comp = result["comparison"]
        self.assertEqual(len(comp["rows"]), 2)
        self.assertIn(comp["best"]["gen_tok_per_s_median"], ("a", "b"))

    def test_unreachable_target_reports_error(self):
        settings = self._settings(
            [TargetConfig(name="dead", base_url="http://127.0.0.1:1/v1", model="x")],
            warmup=False,
        )
        result = asyncio.run(run_benchmark(settings))
        target = result["targets"]["dead"]
        self.assertIn("error", target)
        # 単一ターゲットでもエラーなら comparison は作られない
        self.assertNotIn("comparison", result)

    def test_client_retries_without_stream_options(self):
        # stream_options を拒否するバックエンドでもトークン数の近似で動作する
        from tests import mock_backend

        def rejecting_do_POST(self_handler, *args, **kwargs):
            # stream_options を含むリクエストには 400 を返す
            length = int(self_handler.headers.get("Content-Length", 0) or 0)
            payload = json.loads(self_handler.rfile.read(length) or b"{}")
            if payload.get("stream_options"):
                self_handler.send_response(400)
                body = json.dumps({"error": {"message": "stream_options is not supported"}}).encode()
                self_handler.send_header("Content-Type", "application/json")
                self_handler.send_header("Content-Length", str(len(body)))
                self_handler.end_headers()
                self_handler.wfile.write(body)
                return
            self_handler._handle_chat(payload)

        with patch.object(mock_backend.Handler, "do_POST", rejecting_do_POST):
            client = OpenAICompatClient(f"http://127.0.0.1:{self.port}/v1")
            import httpx

            async def call():
                limits = httpx.Limits(max_connections=8)
                async with httpx.AsyncClient(timeout=30.0, limits=limits) as http:
                    res = await client.stream_chat(
                        http, "mock-model", [{"role": "user", "content": "hello"}], 16
                    )
                    return res

            res = asyncio.run(call())
            self.assertIsNone(res.completion_tokens)  # usage は取得できない
            self.assertGreater(res.content_chunks, 0)
            self.assertGreater(res.ttft, 0)
            self.assertFalse(client._use_stream_options)


if __name__ == "__main__":
    unittest.main()
