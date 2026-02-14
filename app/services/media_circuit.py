import time
import redis.asyncio as redis
from app.core.config import settings
from app.services.media_errors import MediaRetryableError, MediaErrorCode

_redis = redis.from_url(settings.redis_url, decode_responses=True)

FAIL_WINDOW = 60          # seconds
FAIL_THRESHOLD = 20       # failures in window
OPEN_SECONDS = 120        # circuit open duration


async def check_circuit(key: str):
    state = await _redis.get(f"media_cb:open:{key}")
    if state:
        raise MediaRetryableError(
            MediaErrorCode.CIRCUIT_OPEN,
            "media circuit breaker open",
        )


async def record_failure(key: str):
    now = int(time.time())
    bucket = now // FAIL_WINDOW
    rkey = f"media_cb:fail:{key}:{bucket}"

    count = await _redis.incr(rkey)
    if count == 1:
        await _redis.expire(rkey, FAIL_WINDOW + 5)

    if count >= FAIL_THRESHOLD:
        await _redis.set(
            f"media_cb:open:{key}",
            "1",
            ex=OPEN_SECONDS,
        )