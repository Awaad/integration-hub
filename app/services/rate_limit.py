from __future__ import annotations

import time
import redis.asyncio as redis

from app.core.config import settings


_redis = redis.from_url(settings.redis_url, decode_responses=True)


class MediaRetryableError(Exception):
    pass


async def check_rate_limit(key: str, limit: int, window_seconds: int = 60):
    now = int(time.time())
    bucket = now // window_seconds

    redis_key = f"media_rate:{key}:{bucket}"
    count = await _redis.incr(redis_key)

    if count == 1:
        await _redis.expire(redis_key, window_seconds + 5)

    if count > limit:
        raise MediaRetryableError("rate limit exceeded")