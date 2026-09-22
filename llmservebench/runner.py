"""ベンチマーク実行オーケストレーター (単一/複数ターゲット比較)"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Callable

from .bench import Benchmark, CommonConfig, TargetConfig

SUMMARY_METRICS = [
    ("ttft_s_median", "TTFT (s)", 3),
    ("gen_tok_per_s_median", "生成速度 (tok/s)", 2),
    ("tpot_s_median", "TPOT (s)", 3),
    ("prefill_prompt_tok_per_s_median", "prefill (tok/s)", 0),
    ("parallel_aggregate_tok_per_s_peak", "集約 tok/s (peak)", 2),
]


@dataclass
class BenchSettings:
    mode: str  # "single" or "compare"
    targets: list[TargetConfig]
    common: CommonConfig


def build_comparison(targets: dict) -> dict:
    rows = []
    for name, r in targets.items():
        s = r.get("summary") or {}
        rows.append(
            {
                "name": name,
                "model": r.get("model"),
                "ttft_s_median": s.get("ttft_s_median"),
                "gen_tok_per_s_median": s.get("gen_tok_per_s_median"),
                "tpot_s_median": s.get("tpot_s_median"),
                "prefill_prompt_tok_per_s_median": s.get("prefill_prompt_tok_per_s_median"),
                "parallel_aggregate_tok_per_s_peak": s.get("parallel_aggregate_tok_per_s_peak"),
                "parallel_aggregate_tok_per_s_peak_level": s.get(
                    "parallel_aggregate_tok_per_s_peak_level"
                ),
            }
        )

    def best(metric: str, higher_is_better: bool) -> str | None:
        vals = [(row.get(metric), row["name"]) for row in rows if row.get(metric) is not None]
        if not vals:
            return None
        return (max if higher_is_better else min)(vals)[1]

    return {
        "rows": rows,
        "best": {
            "ttft_s_median": best("ttft_s_median", False),
            "gen_tok_per_s_median": best("gen_tok_per_s_median", True),
            "tpot_s_median": best("tpot_s_median", False),
            "prefill_prompt_tok_per_s_median": best("prefill_prompt_tok_per_s_median", True),
            "parallel_aggregate_tok_per_s_peak": best("parallel_aggregate_tok_per_s_peak", True),
        },
    }


async def run_benchmark(
    settings: BenchSettings, on_event: Callable[[dict], None] | None = None
) -> dict:
    on_event = on_event or (lambda event: None)
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    targets_results: dict = {}

    for target in settings.targets:
        on_event({"type": "target_start", "name": target.name})
        try:
            targets_results[target.name] = await Benchmark(target, settings.common, on_event).run()
        except Exception as e:
            message = f"{type(e).__name__}: {e}"
            on_event({"type": "target_error", "name": target.name, "message": message})
            targets_results[target.name] = {
                "name": target.name,
                "base_url": target.base_url,
                "model": target.model,
                "error": message,
            }
        on_event({"type": "target_end", "name": target.name})

    result = {
        "schema": "llmservebench.v2",
        "mode": settings.mode,
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            **asdict(settings.common),
            "targets": [
                {"name": t.name, "base_url": t.base_url, "model": t.model}
                for t in settings.targets
            ],
        },
        "targets": targets_results,
    }
    if len(targets_results) > 1:
        result["comparison"] = build_comparison(targets_results)
    on_event({"type": "done"})
    return result
