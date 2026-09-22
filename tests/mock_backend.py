"""テスト用モック OpenAI互換バックエンド (SSE ストリーミング, in-process)"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

N_CHUNKS = 24
CHUNK_DELAY = 0.004
PREFILL_BASE_DELAY = 0.02
PREFILL_PER_TOKEN_DELAY = 0.00001


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            body = json.dumps({"data": [{"id": "mock-model"}, {"id": "mock-model-2"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        self._handle_chat(payload)

    def _handle_chat(self, payload):
        prompt_chars = sum(len(m.get("content", "")) for m in payload.get("messages", []))
        prompt_tokens = max(1, prompt_chars // 4)
        time.sleep(PREFILL_BASE_DELAY + prompt_tokens * PREFILL_PER_TOKEN_DELAY)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def sse(obj):
            self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")

        for _ in range(N_CHUNKS):
            sse({
                "id": "c1",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": "tok "}}],
            })
            self.wfile.flush()
            time.sleep(CHUNK_DELAY)

        if payload.get("stream_options"):
            sse({
                "id": "c1",
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": N_CHUNKS,
                    "total_tokens": prompt_tokens + N_CHUNKS,
                },
            })
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def create_test_server():
    """空きポートで ThreadingHTTPServer を作成して (server, port) を返す"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server, server.server_address[1]
