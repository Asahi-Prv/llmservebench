from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from .bench import CommonConfig, TargetConfig
from .report import to_json, to_markdown
from .runner import BenchSettings, run_benchmark
from .server import serve


def _sec(v) -> str:
    return f"{v:.3f}s" if isinstance(v, (int, float)) else "-"


def _rate(v) -> str:
    return f"{v:.1f} tok/s" if isinstance(v, (int, float)) else "-"


def _console_event(event: dict) -> None:
    t = event.get("type")
    if t == "info":
        print(f"[info] {event['message']}")
    elif t == "warn":
        print(f"[warn] {event['message']}")
    elif t == "target_start":
        print(f"##### target: {event.get('name')} #####")
    elif t == "target_error":
        print(f"[error] target '{event.get('name')}': {event.get('message')}")
    elif t == "phase_start":
        name = event.get("name")
        extra = f" (parallelism={event.get('parallelism')})" if name == "parallel" else ""
        print(f"== {name}{extra} ==")
    elif t == "request_done":
        if event.get("ok"):
            if event.get("phase") == "prefill":
                print(
                    f"  #{event.get('index')}: ttft={_sec(event.get('ttft_s'))} "
                    f"prompt={_rate(event.get('prompt_tok_per_s'))}"
                )
            else:
                print(
                    f"  #{event.get('index')}: ttft={_sec(event.get('ttft_s'))} "
                    f"gen={_rate(event.get('gen_tok_per_s'))}"
                )
        else:
            print(f"  #{event.get('index')}: ERROR {event.get('error')}")
    elif t == "run_done":
        print(
            f"  run {event.get('run')}: aggregate={_rate(event.get('aggregate_tok_per_s'))} "
            f"wall={_sec(event.get('wall_time_s'))}"
        )
    elif t == "done":
        print("== done ==")


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--parallel", default="1,2,4,8", help="カンマ区切りの並列数 (例: 1,4,8)")
    p.add_argument("--max-tokens", type=int, default=256, help="生成トークン上限 (デフォルト: 256)")
    p.add_argument("--runs", type=int, default=5, help="単一/prefill計測の繰り返し数 (デフォルト: 5)")
    p.add_argument("--parallel-runs", type=int, default=3, help="並列計測の繰り返し数 (デフォルト: 3)")
    p.add_argument(
        "--prefill-tokens", type=int, default=2048, help="prefill計測の目標プロンプトトークン数 (デフォルト: 2048)"
    )
    p.add_argument("--no-warmup", action="store_true", help="ウォームアップをスキップ")
    p.add_argument(
        "--no-randomize",
        action="store_true",
        help="プロンプトのランダム化 (prefix cache バスト) を無効化",
    )
    p.add_argument("--temperature", type=float, default=None, help="temperature (指定時のみリクエストに含める)")
    p.add_argument("--seed", type=int, default=None, help="乱数シード (プロンプト選択の再現用)")
    p.add_argument("--out", default=None, help="結果JSONの保存先 (デフォルト: results/<タイムスタンプ>.json)")


def build_common(args: argparse.Namespace) -> CommonConfig:
    levels = [int(x) for x in str(args.parallel).split(",") if x.strip()]
    return CommonConfig(
        parallel_levels=levels,
        max_tokens=args.max_tokens,
        runs=args.runs,
        parallel_runs=args.parallel_runs,
        prefill_target_tokens=args.prefill_tokens,
        warmup=not args.no_warmup,
        randomize_prompts=not args.no_randomize,
        temperature=args.temperature,
        seed=args.seed,
    )


def parse_backend(spec: str) -> TargetConfig:
    """name=base_url@model[@api_key] 形式を解析する"""
    if "=" not in spec:
        raise ValueError(f"--backend は name=base_url@model 形式で指定してください: {spec}")
    name, rest = spec.split("=", 1)
    parts = rest.split("@")
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError(f"--backend は name=base_url@model 形式で指定してください: {spec}")
    return TargetConfig(
        name=name.strip(),
        base_url=parts[0].strip(),
        model=parts[1].strip(),
        api_key=parts[2] if len(parts) > 2 and parts[2] else None,
    )


def _save_results(result: dict, out: str | None, label: str) -> None:
    if out is None:
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = str(results_dir / f"{stamp}-{label}.json")
    Path(out).write_text(to_json(result), encoding="utf-8")
    md_path = str(Path(out).with_suffix(".md"))
    Path(md_path).write_text(to_markdown(result), encoding="utf-8")
    print(f"結果を保存: {out}")
    print(f"レポート: {md_path}")


def cmd_run(args: argparse.Namespace) -> int:
    _setup_stdio()
    settings = BenchSettings(
        mode="single",
        targets=[TargetConfig(name="default", base_url=args.base_url, model=args.model, api_key=args.api_key)],
        common=build_common(args),
    )
    return _execute(settings, args.out)


def cmd_compare(args: argparse.Namespace) -> int:
    _setup_stdio()
    try:
        targets = [parse_backend(spec) for spec in args.backend]
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    if len(targets) < 2:
        print("エラー: 比較モードでは --backend を2つ以上指定してください", file=sys.stderr)
        return 2
    settings = BenchSettings(mode="compare", targets=targets, common=build_common(args))
    return _execute(settings, args.out)


def _execute(settings: BenchSettings, out: str | None) -> int:
    try:
        result = asyncio.run(run_benchmark(settings, on_event=_console_event))
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    label = settings.mode if settings.mode == "compare" else (settings.targets[0].name or "run")
    _save_results(result, out, label)
    return 0


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def cmd_serve(args: argparse.Namespace) -> int:
    _setup_stdio()
    serve(args.host, args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="llmservebench", description="LLM推論バックエンド (OpenAI互換API) ベンチマークツール"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="単一バックエンドのベンチマークを実行して結果を保存")
    run_p.add_argument("--base-url", required=True, help="OpenAI互換APIのベースURL (例: http://localhost:8080/v1)")
    run_p.add_argument("--model", required=True, help="モデルID")
    run_p.add_argument("--api-key", default=None, help="APIキー (任意)")
    add_common_args(run_p)
    run_p.set_defaults(func=cmd_run)

    cmp_p = sub.add_parser("compare", help="複数バックエンドを順次実行して比較レポートを作成")
    cmp_p.add_argument(
        "--backend",
        action="append",
        required=True,
        metavar="NAME=BASE_URL@MODEL[@API_KEY]",
        help="例: --backend llama=http://127.0.0.1:8080/v1@qwen2.5-7b (2つ以上指定)",
    )
    add_common_args(cmp_p)
    cmp_p.set_defaults(func=cmd_compare)

    serve_p = sub.add_parser("serve", help="Web UIを起動")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)
