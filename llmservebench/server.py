from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .bench import CommonConfig, TargetConfig
from .client import OpenAICompatClient
from .report import to_json, to_markdown
from .runner import BenchSettings, run_benchmark

WEB_DIR = Path(__file__).resolve().parent / "web"

_state: dict = {"running": False, "events": [], "result": None, "error": None}
_lock = threading.Lock()


def _on_event(event: dict) -> None:
    with _lock:
        _state["events"].append(event)


def _run_bench_sync(settings: BenchSettings) -> None:
    try:
        result = asyncio.run(run_benchmark(settings, on_event=_on_event))
        with _lock:
            _state["result"] = result
            _state["running"] = False
    except Exception as e:
        with _lock:
            _state["error"] = f"{type(e).__name__}: {e}"
            _state["running"] = False


def _make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args) -> None:  # noqa: A002
            pass

        def _send(self, body: bytes, ctype: str, status: int = 200, download: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, obj: dict, status: int = 200) -> None:
            self._send(
                json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _send_file(self, path: Path, ctype: str) -> None:
            if not path.is_file():
                self.send_error(404)
                return
            self._send(path.read_bytes(), ctype)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0) or 0)
            return self.rfile.read(length) if length > 0 else b"{}"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            elif path == "/app.js":
                self._send_file(WEB_DIR / "app.js", "text/javascript; charset=utf-8")
            elif path == "/i18n.js":
                self._send_file(WEB_DIR / "i18n.js", "text/javascript; charset=utf-8")
            elif path == "/style.css":
                self._send_file(WEB_DIR / "style.css", "text/css; charset=utf-8")
            elif path == "/vendor/sashimi.default.theme.css":
                self._send_file(
                    WEB_DIR / "vendor" / "sashimi.default.theme.css", "text/css; charset=utf-8"
                )
            elif path == "/vendor/sashimi.bundle.css":
                self._send_file(WEB_DIR / "vendor" / "sashimi.bundle.css", "text/css; charset=utf-8")
            elif path == "/api/status":
                with _lock:
                    payload = {
                        "running": _state["running"],
                        "events": list(_state["events"]),
                        "result": _state["result"],
                        "error": _state["error"],
                    }
                self._send_json(payload)
            elif path == "/api/report":
                with _lock:
                    result = _state["result"]
                if result is None:
                    self._send_json(
                        {"error": "結果がありません。先にベンチマークを実行してください。"}, 404
                    )
                    return
                qs = parse_qs(urlparse(self.path).query)
                fmt = (qs.get("format") or ["json"])[0]
                if fmt == "markdown":
                    self._send(
                        to_markdown(result).encode("utf-8"),
                        "text/markdown; charset=utf-8",
                        download="llmservebench-report.md",
                    )
                else:
                    self._send(
                        to_json(result).encode("utf-8"),
                        "application/json; charset=utf-8",
                        download="llmservebench-report.json",
                    )
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/run":
                try:
                    cfg_obj = json.loads(self._read_body())
                    targets = [
                        TargetConfig(
                            name=str(t.get("name") or f"target{i + 1}"),
                            base_url=str(t["base_url"]),
                            model=str(t["model"]),
                            api_key=t.get("api_key") or None,
                        )
                        for i, t in enumerate(cfg_obj.get("targets", []))
                    ]
                    if not targets:
                        self._send_json({"error": "targets が空です"}, 400)
                        return
                    common = CommonConfig(
                        parallel_levels=[int(x) for x in cfg_obj.get("parallel_levels", [1, 2, 4, 8])],
                        max_tokens=int(cfg_obj.get("max_tokens", 256)),
                        runs=int(cfg_obj.get("runs", 5)),
                        parallel_runs=int(cfg_obj.get("parallel_runs", 3)),
                        prefill_target_tokens=int(cfg_obj.get("prefill_tokens", 2048)),
                        warmup=bool(cfg_obj.get("warmup", True)),
                        randomize_prompts=bool(cfg_obj.get("randomize_prompts", True)),
                        temperature=cfg_obj.get("temperature"),
                        seed=cfg_obj.get("seed"),
                    )
                    mode = "compare" if len(targets) > 1 else "single"
                    settings = BenchSettings(mode=mode, targets=targets, common=common)
                except Exception as e:
                    self._send_json({"error": f"設定が不正です: {e}"}, 400)
                    return
                with _lock:
                    if _state["running"]:
                        self._send_json({"error": "ベンチマークが実行中です"}, 409)
                        return
                    _state["running"] = True
                    _state["events"] = []
                    _state["result"] = None
                    _state["error"] = None
                threading.Thread(target=_run_bench_sync, args=(settings,), daemon=True).start()
                self._send_json({"started": True, "mode": mode})
            elif path == "/api/models":
                try:
                    cfg_obj = json.loads(self._read_body())
                    client = OpenAICompatClient(
                        str(cfg_obj["base_url"]), cfg_obj.get("api_key") or None
                    )
                    models = asyncio.run(client.list_models())
                    self._send_json({"models": models})
                except Exception as e:
                    self._send_json({"error": f"{type(e).__name__}: {e}"}, 502)
            else:
                self.send_error(404)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), _make_handler())
    print(f"llmservebench Web UI: http://{host}:{port}/  (Ctrl+C で終了)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
