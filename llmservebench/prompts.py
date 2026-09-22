"""ベンチマーク用プロンプトの生成とランダム化 (prefix cache 対策)"""

from __future__ import annotations

import random
import string

_PREFILL_BASE = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquor jugs. "
    "How vexingly quick daft zebras jump! "
    "Sphinx of black quartz, judge my vow. "
)

SHORT_PROMPTS = [
    "You are a helpful assistant. Write a detailed product review for a "
    "fictional mechanical keyboard. Include at least six sentences.",
    "You are a helpful assistant. Explain how a four-stroke engine works to "
    "a curious beginner. Include at least six sentences.",
    "You are a helpful assistant. Describe a morning walk through a foggy "
    "coastal town. Include at least six sentences.",
    "You are a helpful assistant. Summarize why the sky changes color at "
    "sunset. Include at least six sentences.",
]

WARMUP_PROMPT = "Say hello."


def _random_tag(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(12))


def short_prompt(rng: random.Random) -> str:
    # ランダムな接頭辞でプロンプトキャッシュ (prefix cache) を無効化する
    return f"[{_random_tag(rng)}] {random.choice(SHORT_PROMPTS)}"


def long_prompt(target_tokens: int, rng: random.Random) -> str:
    chars = max(200, target_tokens * 4)
    reps = chars // len(_PREFILL_BASE) + 1
    text = (_PREFILL_BASE * reps)[:chars]
    # 接頭辞側にランダム部分を置かないと prefix cache が効いてしまうため先頭に置く
    return f"[{_random_tag(rng)}] {text}"


def fixed_long_prompt(target_tokens: int) -> str:
    chars = max(200, target_tokens * 4)
    reps = chars // len(_PREFILL_BASE) + 1
    return (_PREFILL_BASE * reps)[:chars]
