# llmservebench

Benchmark and compare LLM inference backends that speak the OpenAI-compatible
API — llama.cpp (`llama-server`), Ollama, LM Studio, vLLM, and others — from
the client side, with both a CLI and a built-in Web UI.

## Features

- **Metrics measured per request**
  - TTFT (time to first token)
  - Generation speed (tok/s, decode phase only)
  - TPOT (time per output token) and ITL (inter-token latency) percentiles
  - Prefill speed (prompt tok/s, measured with a long prompt + `max_tokens=1`)
  - Aggregate throughput under concurrency (1 / 2 / 4 / 8 ... parallel requests)
- **Compare mode**: benchmark several backends sequentially with identical
  settings and get a single comparison report (best value per metric highlighted)
- **Web UI**: live progress, summary cards, tables, and hand-rolled SVG charts
  (no frontend framework, no build step)
- **Prefix-cache busting**: prompts are randomized per request by default so
  server-side prompt/prefix caches don't distort the numbers
- **Lightweight**: the only dependency is `httpx`
- **Reports**: JSON + Markdown export

## Install

```bash
git clone <this repository>
cd llmservebench
pip install -e .
```

Requires Python 3.10+.

## Quick start

### Web UI

```bash
llmservebench serve --port 8000
```

Open `http://127.0.0.1:8000/`, enter the base URL (e.g. `http://localhost:8080/v1`)
and model ID, then press **Run**. The "Backend comparison" tab lets you run
several backends in one go and shows a comparison table with charts.

### CLI

```bash
# single backend
llmservebench run --base-url http://localhost:8080/v1 --model qwen2.5-7b-instruct

# compare multiple backends (name=base_url@model)
llmservebench compare \
  --backend "llamacpp=http://127.0.0.1:8080/v1@qwen2.5-7b-instruct" \
  --backend "ollama=http://127.0.0.1:11434/v1@qwen2.5:7b-instruct" \
  --backend "vllm=http://127.0.0.1:8001/v1@Qwen/Qwen2.5-7B-Instruct"
```

Useful options:

| Option | Default | Description |
|---|---|---|
| `--parallel` | `1,2,4,8` | Comma-separated concurrency levels |
| `--max-tokens` | `256` | Max generated tokens per request |
| `--runs` | `5` | Repetitions for single/prefill measurements |
| `--parallel-runs` | `3` | Repetitions per parallel level |
| `--prefill-tokens` | `2048` | Target prompt tokens for the prefill test |
| `--no-warmup` | off | Skip the warmup request |
| `--no-randomize` | off | Disable prompt randomization (not recommended) |
| `--temperature` | none | Sent only when specified |
| `--seed` | none | Seed for reproducible prompt selection |
| `--out` | `results/<timestamp>.json` | Output path (`.md` is written next to it) |

Results are saved as JSON + Markdown under `results/`.

## What is measured (methodology)

Each benchmark run consists of:

1. **Warmup** — one short request to load the model / warm connections.
2. **Single stream** — N sequential requests with a short prompt. Reports
   TTFT, generation tok/s (decode phase only), TPOT, and ITL percentiles.
3. **Prefill** — N requests with a long prompt (~`--prefill-tokens` tokens,
   randomized prefix to defeat prompt caching) and `max_tokens=1`. Reports
   prompt tok/s (`prompt_tokens / TTFT`).
4. **Parallel** — for each concurrency level, `--parallel-runs` rounds of
   concurrent requests. Reports aggregate tok/s (total tokens / wall time)
   and per-request stats.

Token counts are taken from the `usage` field (`stream_options:
{"include_usage": true}`). If a backend does not report usage, the number of
streamed content chunks is used as an approximation (1 chunk ≈ 1 token), which
underestimates tok/s for backends that send multiple tokens per chunk.
Unsupported parameters (`stream_options`, `max_tokens`) are detected from
400 responses and retried automatically.

## Limitations

- All measurements are **client-side**: latencies include network round-trip
  and client scheduling overhead. Run the tool on the same machine or LAN as
  the backend for fair comparisons.
- Aggregate throughput can be limited by the client's connection pool rather
  than the server for very high concurrency levels.
- This tool benchmarks the **serving stack** (HTTP API level). For raw
  kernel/hardware-level numbers use `llama-bench` or similar tools.
- Benchmarks are sensitive to model, quantization, context length, GPU thermal
  state, and backend configuration (e.g. `-np` in llama.cpp). Change one
  variable at a time.

## Development

```bash
python -m unittest discover -s tests -t . -v
```

The end-to-end tests spin up a mock OpenAI-compatible backend (SSE streaming)
in-process, so no real backend or GPU is needed.

## License

MIT — see [LICENSE](LICENSE).
