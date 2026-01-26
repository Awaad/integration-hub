from __future__ import annotations
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

@dataclass
class FeedBuildStats:
    skipped_by_reason: Counter[str]
    warnings_by_code: Counter[str]
    parse_ok: bool
    parse_ms: int

def summarize_warnings(warnings: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for w in warnings:
        code = str(w.get("code") or "UNKNOWN")
        c[code] += 1
    return c

def summarize_skips(skipped: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for s in skipped:
        reason = str(s.get("reason") or "unknown")
        c[reason] += 1
    return c

class Timer:
    def __enter__(self):
        self._t0 = time.perf_counter()
        self.ms = 0
        return self
    def __exit__(self, exc_type, exc, tb):
        self.ms = int((time.perf_counter() - self._t0) * 1000)
