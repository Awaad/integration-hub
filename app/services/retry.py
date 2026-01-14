import random
from datetime import timedelta

def compute_backoff_seconds(attempt: int, base: int = 10, cap: int = 900) -> int:
    # exponential backoff with jitter
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = random.randint(0, min(30, exp // 3))
    return exp + jitter
