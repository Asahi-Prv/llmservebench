from __future__ import annotations

import asyncio
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

import httpx

from . import prompts
from .client import OpenAICompatClient


@dataclass
class TargetConfig:
    name: str
    base_url: str
    model: str
    api_key: str | None = None


@dataclass
class CommonConfig:
    parallel_levels: list[int] = field(default_factory=lambda: [1, 2, 4, 8])
    max_tokens: int = 256
    runs: int = 5  # 単一/prefill計測の繰り返し数
    parallel_runs: int = 3  # 並列計測の繰り返し数
    prefill_target_tokens: int = 2048
    warmup: bool = True
    randomize_prompts: bool = True  # prefix cache バスト
    temperature: float | None = None  # 指定時のみ送信
    seed: int | None = None  # プロンプト選択の再現用


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20)[-1]


def _stats(values: list[float | None]) -> dict:
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return {"mean": None, "median": None, "p95": None, "min": None, "max": None}
    return {
        "mean": statistics.fmean(vs),
        "median": statistics.median(vs),
        "p95": _p95(vs),
        "min": vs[0],
        "max": vs[-1],
    }


def _summarize(records: list[dict]) -> dict:
    ok = [r for r in records if r.get("ok")]
    all_itls = [v for r in ok for v in (r.get("itls") or [])]
    return {
        "requests": len(records),
        "ok_requests": len(ok),
        "ttft": _stats([r.get("ttft_s") for r in ok]),
        "gen_tok_per_s": _stats([r.get("gen_tok_per_s") for r in ok]),
        "tpot": _stats([r.get("tpot_s") for r in ok]),
        "itl": _stats(all_itls),
        "prompt_tok_per_s": _stats([r.get("prompt_tok_per_s") for r in ok]),
        "completion_tokens": _stats([r.get("completion_tokens") for r in ok]),
    }


class Benchmark:
    def __init__(
        self,
        target: TargetConfig,
        common: CommonConfig,
        on_event: Callable[[dict], None] | None = None,
    ):
        self.target = target
        self.cfg = common
        self._on_event = on_event or (lambda event: None)
        self._rng = random.Random(common.seed)

    def _emit(self, event: dict) -> None:
        try:
            self._on_event(event)
        except Exception:
            pass

    def _gen_prompt(self) -> str:
        if self.cfg.randomize_prompts:
            return prompts.short_prompt(self._rng)
        return prompts.SHORT_PROMPTS[0]

    def _prefill_prompt(self) -> str:
        if self.cfg.randomize_prompts:
            return prompts.long_prompt(self.cfg.prefill_target_tokens, self._rng)
        return prompts.fixed_long_prompt(self.cfg.prefill_target_tokens)

    async def run(self) -> dict:
        cfg = self.cfg
        phases: dict = {}
        limits = httpx.Limits(max_connections=128, max_keepalive_connections=128)
        timeout = httpx.Timeout(300.0, connect=10.0)
        client = OpenAICompatClient(self.target.base_url, self.target.api_key)

        async with httpx.AsyncClient(timeout=timeout, limits=limits) as http:
            models = await client.list_models()
            self._emit(
                {
                    "type": "info",
                    "message": f"[{self.target.name}] 接続OK: {self.target.base_url} (models: {len(models)})",
                }
            )
            if models and self.target.model not in models:
                self._emit(
                    {
                        "type": "warn",
                        "message": f"[{self.target.name}] モデル '{self.target.model}' は /v1/models に見つかりません "
                        f"({', '.join(models[:5])})",
                    }
                )

            if cfg.warmup:
                self._emit({"type": "phase_start", "name": "warmup"})
                try:
                    await client.stream_chat(
                        http, self.target.model, [{"role": "user", "content": prompts.WARMUP_PROMPT}], 16
                    )
                    self._emit({"type": "phase_end", "name": "warmup"})
                except Exception as e:
                    self._emit({"type": "phase_end", "name": "warmup"})
                    self._emit({"type": "warn", "message": f"ウォームアップ失敗: {e}"})

            phases["single"] = await self._phase_single(client, http)
            phases["prefill"] = await self._phase_prefill(client, http)
            parallel: dict = {}
            for level in cfg.parallel_levels:
                if level < 1:
                    continue
                parallel[str(level)] = await self._phase_parallel(client, http, level)
            phases["parallel"] = parallel

        result = {
            "name": self.target.name,
            "base_url": self.target.base_url,
            "model": self.target.model,
            "phases": phases,
        }
        result["summary"] = self._build_summary(phases)
        return result

    async def _one_request(
        self,
        client: OpenAICompatClient,
        http: httpx.AsyncClient,
        messages: list[dict],
        max_tokens: int,
    ) -> dict:
        try:
            res = await client.stream_chat(
                http, self.target.model, messages, max_tokens, temperature=self.cfg.temperature
            )
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "ttft_s": None,
                "gen_tok_per_s": None,
                "tpot_s": None,
                "prompt_tok_per_s": None,
                "completion_tokens": None,
                "prompt_tokens": None,
                "total_time_s": None,
                "itls": [],
            }
        gen_tok_per_s = None
        if res.gen_time > 0:
            tokens = res.completion_tokens if res.completion_tokens is not None else res.content_chunks
            gen_tok_per_s = tokens / res.gen_time
        prompt_tok_per_s = None
        if res.prompt_tokens and res.ttft > 0:
            prompt_tok_per_s = res.prompt_tokens / res.ttft
        return {
            "ok": True,
            "error": None,
            "ttft_s": res.ttft,
            "gen_tok_per_s": gen_tok_per_s,
            "tpot_s": res.tpot,
            "prompt_tok_per_s": prompt_tok_per_s,
            "completion_tokens": res.completion_tokens,
            "prompt_tokens": res.prompt_tokens,
            "total_time_s": res.total_time,
            "itls": [round(x, 6) for x in res.itls],
        }

    async def _phase_single(self, client: OpenAICompatClient, http: httpx.AsyncClient) -> dict:
        cfg = self.cfg
        records: list[dict] = []
        self._emit({"type": "phase_start", "name": "single", "runs": cfg.runs})
        phase_start = time.perf_counter()
        total_tokens = 0
        for i in range(cfg.runs):
            messages = [{"role": "user", "content": self._gen_prompt()}]
            record = await self._one_request(client, http, messages, cfg.max_tokens)
            records.append(record)
            total_tokens += record.get("completion_tokens") or 0
            self._emit({"type": "request_done", "phase": "single", "index": i + 1, **record})
        wall = time.perf_counter() - phase_start
        summary = _summarize(records)
        summary["aggregate_tok_per_s"] = (total_tokens / wall) if wall > 0 else None
        summary["wall_time_s"] = wall
        self._emit({"type": "phase_end", "name": "single"})
        return summary

    async def _phase_prefill(self, client: OpenAICompatClient, http: httpx.AsyncClient) -> dict:
        cfg = self.cfg
        records: list[dict] = []
        self._emit(
            {
                "type": "phase_start",
                "name": "prefill",
                "runs": cfg.runs,
                "prompt_tokens_est": cfg.prefill_target_tokens,
            }
        )
        for i in range(cfg.runs):
            messages = [{"role": "user", "content": self._prefill_prompt()}]
            record = await self._one_request(client, http, messages, 1)
            records.append(record)
            self._emit({"type": "request_done", "phase": "prefill", "index": i + 1, **record})
        summary = _summarize(records)
        self._emit({"type": "phase_end", "name": "prefill"})
        return summary

    async def _phase_parallel(
        self, client: OpenAICompatClient, http: httpx.AsyncClient, level: int
    ) -> dict:
        cfg = self.cfg
        all_records: list[dict] = []
        self._emit(
            {"type": "phase_start", "name": "parallel", "parallelism": level, "runs": cfg.parallel_runs}
        )
        peak: float | None = None
        for i in range(cfg.parallel_runs):
            phase_start = time.perf_counter()
            tasks = []
            for _ in range(level):
                messages = [{"role": "user", "content": self._gen_prompt()}]
                tasks.append(self._one_request(client, http, messages, cfg.max_tokens))
            records = await asyncio.gather(*tasks)
            wall = time.perf_counter() - phase_start
            total_tokens = sum(r.get("completion_tokens") or 0 for r in records)
            agg = (total_tokens / wall) if wall > 0 else None
            if agg is not None and (peak is None or agg > peak):
                peak = agg
            for j, r in enumerate(records):
                r["parallelism"] = level
                self._emit(
                    {"type": "request_done", "phase": "parallel", "parallelism": level, "index": j + 1, **r}
                )
            all_records.extend(records)
            self._emit(
                {
                    "type": "run_done",
                    "phase": "parallel",
                    "parallelism": level,
                    "run": i + 1,
                    "aggregate_tok_per_s": agg,
                    "wall_time_s": wall,
                }
            )
        summary = _summarize(all_records)
        summary["aggregate_tok_per_s"] = peak
        summary["parallelism"] = level
        self._emit({"type": "phase_end", "name": "parallel", "parallelism": level})
        return summary

    @staticmethod
    def _build_summary(phases: dict) -> dict:
        single = phases.get("single") or {}
        prefill = phases.get("prefill") or {}
        parallel = phases.get("parallel") or {}
        best_level: int | None = None
        best_agg: float | None = None
        for level, p in parallel.items():
            agg = p.get("aggregate_tok_per_s")
            if agg is not None and (best_agg is None or agg > best_agg):
                best_agg, best_level = agg, int(level)
        return {
            "ttft_s_median": (single.get("ttft") or {}).get("median"),
            "gen_tok_per_s_median": (single.get("gen_tok_per_s") or {}).get("median"),
            "tpot_s_median": (single.get("tpot") or {}).get("median"),
            "prefill_prompt_tok_per_s_median": (prefill.get("prompt_tok_per_s") or {}).get("median"),
            "parallel_aggregate_tok_per_s_peak": best_agg,
            "parallel_aggregate_tok_per_s_peak_level": best_level,
        }
