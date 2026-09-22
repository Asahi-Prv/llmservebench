from __future__ import annotations

import json
import random
import unittest

from llmservebench import prompts, report
from llmservebench.bench import _p95, _stats
from llmservebench.runner import SUMMARY_METRICS, build_comparison


class StatsTests(unittest.TestCase):
    def test_p95_empty(self):
        self.assertIsNone(_p95([]))

    def test_p95_single(self):
        self.assertEqual(_p95([1.0]), 1.0)

    def test_p95_many(self):
        vals = [float(i) for i in range(100)]
        self.assertTrue(93.0 <= _p95(vals) <= 96.0)

    def test_stats_basic(self):
        s = _stats([1.0, 2.0, 3.0])
        self.assertEqual(s["median"], 2.0)
        self.assertEqual(s["mean"], 2.0)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 3.0)

    def test_stats_skips_none(self):
        s = _stats([None, 2.0, None])
        self.assertEqual(s["median"], 2.0)
        self.assertEqual(s["min"], 2.0)

    def test_stats_all_none(self):
        s = _stats([None, None])
        self.assertIsNone(s["median"])
        self.assertIsNone(s["p95"])


class PromptTests(unittest.TestCase):
    def test_long_prompt_reaches_target_length(self):
        p = prompts.long_prompt(2048, random.Random(0))
        self.assertGreaterEqual(len(p), 2048 * 4)

    def test_randomized_prompts_differ(self):
        p1 = prompts.long_prompt(256, random.Random(1))
        p2 = prompts.long_prompt(256, random.Random(2))
        self.assertNotEqual(p1, p2)

    def test_random_prefix_comes_first(self):
        # prefix cache バストにはランダム部分が先頭に来る必要がある
        p = prompts.long_prompt(256, random.Random(1))
        self.assertTrue(p.startswith("["))
        s = prompts.short_prompt(random.Random(1))
        self.assertTrue(s.startswith("["))

    def test_fixed_long_prompt_is_stable(self):
        self.assertEqual(prompts.fixed_long_prompt(256), prompts.fixed_long_prompt(256))


class ComparisonTests(unittest.TestCase):
    @staticmethod
    def _summary(ttft, gen, tpot, prefill, peak, level):
        return {
            "ttft_s_median": ttft,
            "gen_tok_per_s_median": gen,
            "tpot_s_median": tpot,
            "prefill_prompt_tok_per_s_median": prefill,
            "parallel_aggregate_tok_per_s_peak": peak,
            "parallel_aggregate_tok_per_s_peak_level": level,
        }

    def test_best_per_metric(self):
        targets = {
            "slow": {
                "model": "m1",
                "summary": self._summary(0.5, 10.0, 0.1, 100.0, 20.0, 4),
            },
            "fast": {
                "model": "m2",
                "summary": self._summary(0.2, 30.0, 0.05, 200.0, 50.0, 8),
            },
        }
        comp = build_comparison(targets)
        self.assertEqual(len(comp["rows"]), 2)
        # 低いほど良い指標
        self.assertEqual(comp["best"]["ttft_s_median"], "fast")
        self.assertEqual(comp["best"]["tpot_s_median"], "fast")
        # 高いほど良い指標
        self.assertEqual(comp["best"]["gen_tok_per_s_median"], "fast")
        self.assertEqual(comp["best"]["prefill_prompt_tok_per_s_median"], "fast")
        self.assertEqual(comp["best"]["parallel_aggregate_tok_per_s_peak"], "fast")

    def test_best_skips_error_targets(self):
        targets = {
            "broken": {"model": "m1", "error": "connection refused", "summary": None},
            "ok": {
                "model": "m2",
                "summary": self._summary(0.2, 30.0, 0.05, 200.0, 50.0, 8),
            },
        }
        comp = build_comparison(targets)
        self.assertEqual(comp["best"]["gen_tok_per_s_median"], "ok")
        self.assertIsNone(comp["rows"][0]["ttft_s_median"])

    def test_summary_metrics_shape(self):
        for metric, label, digits in SUMMARY_METRICS:
            self.assertIsInstance(metric, str)
            self.assertIsInstance(label, str)
            self.assertIn(digits, (0, 2, 3))


class ReportTests(unittest.TestCase):
    @staticmethod
    def _sample_result():
        return {
            "schema": "llmservebench.v2",
            "mode": "compare",
            "started_at": "2026-09-22T12:00:00",
            "finished_at": "2026-09-22T12:01:00",
            "config": {
                "max_tokens": 256,
                "runs": 5,
                "parallel_runs": 3,
                "randomize_prompts": True,
                "targets": [
                    {"name": "a", "base_url": "http://x/v1", "model": "m1"},
                    {"name": "b", "base_url": "http://y/v1", "model": "m2"},
                ],
            },
            "targets": {
                "a": {
                    "name": "a",
                    "base_url": "http://x/v1",
                    "model": "m1",
                    "phases": {
                        "single": {
                            "requests": 5,
                            "ok_requests": 5,
                            "ttft": {"mean": 0.1, "median": 0.1, "p95": 0.12, "min": 0.09, "max": 0.12},
                            "gen_tok_per_s": {"mean": 100.0, "median": 100.0, "p95": 110.0, "min": 90.0, "max": 110.0},
                            "tpot": {"mean": 0.01, "median": 0.01, "p95": 0.011, "min": 0.009, "max": 0.011},
                            "itl": {"mean": 0.01, "median": 0.01, "p95": 0.012, "min": 0.008, "max": 0.012},
                            "completion_tokens": {"mean": 24.0, "median": 24.0, "p95": 24.0, "min": 24.0, "max": 24.0},
                        },
                        "prefill": {
                            "requests": 5,
                            "ok_requests": 5,
                            "prompt_tok_per_s": {"mean": 5000.0, "median": 5000.0, "p95": 5200.0, "min": 4800.0, "max": 5200.0},
                        },
                        "parallel": {
                            "1": {
                                "requests": 3,
                                "ok_requests": 3,
                                "aggregate_tok_per_s": 90.0,
                                "ttft": {"median": 0.1},
                                "gen_tok_per_s": {"median": 100.0},
                            }
                        },
                    },
                    "summary": {
                        "ttft_s_median": 0.1,
                        "gen_tok_per_s_median": 100.0,
                        "tpot_s_median": 0.01,
                        "prefill_prompt_tok_per_s_median": 5000.0,
                        "parallel_aggregate_tok_per_s_peak": 90.0,
                        "parallel_aggregate_tok_per_s_peak_level": 1,
                    },
                },
                "b": {
                    "name": "b",
                    "base_url": "http://y/v1",
                    "model": "m2",
                    "error": "connection refused",
                },
            },
            "comparison": build_comparison({
                "a": {"model": "m1", "summary": {
                    "ttft_s_median": 0.1, "gen_tok_per_s_median": 100.0, "tpot_s_median": 0.01,
                    "prefill_prompt_tok_per_s_median": 5000.0,
                    "parallel_aggregate_tok_per_s_peak": 90.0, "parallel_aggregate_tok_per_s_peak_level": 1,
                }},
                "b": {"model": "m2", "summary": None},
            }),
        }

    def test_markdown_sections(self):
        md = report.to_markdown(self._sample_result())
        self.assertIn("# llmservebench Report", md)
        self.assertIn("## 比較", md)
        self.assertIn("## a (m1)", md)
        self.assertIn("TPOT (s)", md)
        self.assertIn("ITL (s)", md)
        # errorターゲットは比較表には載るが詳細セクションはスキップ
        self.assertNotIn("## b (m2)", md)

    def test_markdown_highlights_best(self):
        md = report.to_markdown(self._sample_result())
        self.assertIn("**100.00**", md)

    def test_json_roundtrip(self):
        result = self._sample_result()
        data = json.loads(report.to_json(result))
        self.assertEqual(data["schema"], "llmservebench.v2")
        self.assertEqual(len(data["targets"]), 2)

    def test_json_does_not_leak_api_key(self):
        result = self._sample_result()
        # config.targets には api_key を含めない
        text = report.to_json(result)
        self.assertNotIn("api_key", text)


if __name__ == "__main__":
    unittest.main()
