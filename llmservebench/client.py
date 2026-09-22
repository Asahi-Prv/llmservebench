from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx


class BackendError(RuntimeError):
    pass


class UnsupportedParam(BackendError):
    def __init__(self, param: str):
        super().__init__(f"param not supported: {param}")
        self.param = param


@dataclass
class StreamResult:
    ttft: float  # 最初のコンテンツトークンまでの秒数
    gen_time: float  # 初トークンから完了までの秒数
    total_time: float
    content_chunks: int  # 受信したコンテンツdelta数 (usage未対応時の近似トークン数)
    completion_tokens: int | None  # usage から (未報告なら None)
    prompt_tokens: int | None
    itls: list[float]  # トークン間レイテンシ (秒)
    tpot: float | None  # (total - ttft) / (n_tokens - 1)


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._use_stream_options = True
        self._use_max_tokens = True

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(self.base_url + "/models", headers=self._headers())
        if resp.status_code != 200:
            raise BackendError(
                f"GET /models -> HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise BackendError(f"/models の応答がJSONではありません: {e}") from e
        return [m.get("id") or "?" for m in data.get("data", [])]

    async def stream_chat(
        self,
        http: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float | None = None,
    ) -> StreamResult:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if self._use_max_tokens:
            payload["max_tokens"] = max_tokens
        else:
            payload["max_completion_tokens"] = max_tokens
        if self._use_stream_options:
            payload["stream_options"] = {"include_usage": True}
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            return await self._stream(http, payload)
        except UnsupportedParam as e:
            if e.param == "stream_options":
                self._use_stream_options = False
                payload.pop("stream_options", None)
            elif e.param == "max_tokens":
                self._use_max_tokens = False
                payload.pop("max_tokens", None)
                payload["max_completion_tokens"] = max_tokens
            return await self._stream(http, payload)

    async def _stream(self, http: httpx.AsyncClient, payload: dict) -> StreamResult:
        ttft: float | None = None
        chunks = 0
        usage: dict | None = None
        itls: list[float] = []
        last_ts: float | None = None
        first_lines: list[str] = []
        start = time.perf_counter()

        async with http.stream(
            "POST", self.base_url + "/chat/completions", json=payload, headers=self._headers()
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                low = body.lower()
                if resp.status_code == 400 and "stream_options" in low and "stream_options" in payload:
                    raise UnsupportedParam("stream_options")
                if resp.status_code == 400 and "max_tokens" in low and "max_tokens" in payload:
                    raise UnsupportedParam("max_tokens")
                raise BackendError(
                    f"POST /chat/completions -> HTTP {resp.status_code}: {body[:300]}"
                )
            async for line in resp.aiter_lines():
                if len(first_lines) < 5:
                    first_lines.append(line[:200])
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                u = obj.get("usage")
                if isinstance(u, dict) and u:
                    usage = u
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content") or delta.get("reasoning_content")
                if piece:
                    chunks += 1
                    now = time.perf_counter()
                    if ttft is None:
                        ttft = now - start
                    else:
                        itls.append(now - last_ts)
                    last_ts = now

        total = time.perf_counter() - start
        if ttft is None:
            raise BackendError(
                "応答にコンテンツが含まれません (ストリーミング非対応/空応答の可能性): "
                + " | ".join(s for s in first_lines if s)
            )
        completion_tokens = usage.get("completion_tokens") if usage else None
        prompt_tokens = usage.get("prompt_tokens") if usage else None

        tpot: float | None = None
        n_tokens = completion_tokens if completion_tokens is not None else chunks
        if n_tokens >= 2 and total > ttft:
            tpot = (total - ttft) / (n_tokens - 1)

        return StreamResult(
            ttft=ttft,
            gen_time=max(0.0, total - ttft),
            total_time=total,
            content_chunks=chunks,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            itls=itls,
            tpot=tpot,
        )
