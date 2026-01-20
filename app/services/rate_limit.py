from __future__ import annotations
import time
from dataclasses import dataclass

import redis.asyncio as redis

@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_seconds: int

class TokenRateLimiter:
    def __init__(self, redis_url: str):
        self.r = redis.from_url(redis_url, decode_responses=True)

    async def allow(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(time.time())
        window = now // window_seconds
        rkey = f"rl:{key}:{window}"

        # INCR with expiry
        val = await self.r.incr(rkey)
        if val == 1:
            await self.r.expire(rkey, window_seconds)

        remaining = max(0, limit - val)
        reset = window_seconds - (now % window_seconds)
        return RateLimitResult(allowed=val <= limit, remaining=remaining, reset_seconds=reset)
