from __future__ import annotations

import json

from .runner import SUMMARY_METRICS


def _fmt(v, digits: int = 2, suffix: str = "") -> str:
    if v is None:
        return "-"
    return f"{v:.{digits}f}{suffix}"


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def to_markdown(result: dict) -> str:
    cfg = result.get("config", {})
    targets = result.get("targets") or {}
    lines: list[str] = []

    lines.append("# llmservebench Report")
    lines.append("")
    lines.append(f"- 実行時刻: {result.get('started_at', '-')} 〜 {result.get('finished_at', '-')}")
    lines.append(f"- Mode: {result.get('mode', '-')}")
    for t in cfg.get("targets", []):
        lines.append(
            f"- Target `{t.get('name', '-')}`: `{t.get('base_url', '-')}` / model `{t.get('model', '-')}`"
        )
    lines.append(
        f"- max_tokens: {cfg.get('max_tokens', '-')}, runs: {cfg.get('runs', '-')}, "
        f"parallel_runs: {cfg.get('parallel_runs', '-')}, randomize_prompts: {cfg.get('randomize_prompts', '-')}"
    )
    lines.append("")

    comparison = result.get("comparison")
    if comparison:
        best = comparison.get("best") or {}
        rows = comparison.get("rows") or []
        lines.append("## 比較 (太字が各指標の最良値)")
        lines.append("")
        header = "| target | model | " + " | ".join(label for _, label, _ in SUMMARY_METRICS) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (2 + len(SUMMARY_METRICS)))
        for row in rows:
            name = row.get("name", "-")
            cells = []
            for metric, _, digits in SUMMARY_METRICS:
                v = row.get(metric)
                s = _fmt(v, digits)
                if v is not None and best.get(metric) == name:
                    s = f"**{s}**"
                if metric == "parallel_aggregate_tok_per_s_peak" and v is not None:
                    level = row.get("parallel_aggregate_tok_per_s_peak_level")
                    if level is not None:
                        s += f" (p={level})"
                cells.append(s)
            lines.append(f"| {name} | {row.get('model', '-')} | " + " | ".join(cells) + " |")
        lines.append("")

    for name, r in targets.items():
        phases = r.get("phases") or {}
        if not phases:
            continue
        model = r.get("model", "-")
        lines.append(f"## {name} ({model})")
        lines.append("")

        single = phases.get("single") or {}
        if single:
            lines.append("### 単一ストリーム")
            lines.append("")
            lines.append("| 指標 | mean | median | p95 | min | max |")
            lines.append("|---|---|---|---|---|---|")
            for key, label, digits in (
                ("ttft", "TTFT (s)", 3),
                ("gen_tok_per_s", "生成速度 (tok/s)", 2),
                ("tpot", "TPOT (s)", 3),
                ("itl", "ITL (s)", 3),
                ("completion_tokens", "completion tokens", 1),
            ):
                s = single.get(key) or {}
                cells = " | ".join(
                    _fmt(s.get(k), digits) for k in ("mean", "median", "p95", "min", "max")
                )
                lines.append(f"| {label} | {cells} |")
            lines.append("")

        prefill = phases.get("prefill") or {}
        if prefill:
            s = prefill.get("prompt_tok_per_s") or {}
            lines.append("### prefill (長プロンプト)")
            lines.append("")
            lines.append("| 指標 | mean | median | p95 | min | max |")
            lines.append("|---|---|---|---|---|---|")
            cells = " | ".join(_fmt(s.get(k), 0) for k in ("mean", "median", "p95", "min", "max"))
            lines.append(f"| prompt tok/s | {cells} |")
            lines.append("")

        parallel = phases.get("parallel") or {}
        if parallel:
            lines.append("### 並列スループット")
            lines.append("")
            lines.append(
                "| parallelism | 集約 tok/s (peak) | TTFT median (s) | per-req tok/s median | ok/total |"
            )
            lines.append("|---|---|---|---|---|")
            for level in sorted(parallel, key=lambda x: int(x)):
                p = parallel[level]
                tt = (p.get("ttft") or {}).get("median")
                gr = (p.get("gen_tok_per_s") or {}).get("median")
                lines.append(
                    f"| {level} | {_fmt(p.get('aggregate_tok_per_s'))} | {_fmt(tt, 3)} | {_fmt(gr)} | "
                    f"{p.get('ok_requests', '-')}/{p.get('requests', '-')} |"
                )
            lines.append("")

    return "\n".join(lines)
