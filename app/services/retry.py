from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func


@dataclass(frozen=True)
class RetryPlan:
    attempts_col: str
    next_at_col: str
    started_at_col: Optional[str] = None
    error_col: Optional[str] = None



def compute_backoff_seconds(attempt: int, base: int = 10, cap: int = 900, rng: random.Random | None = None) -> int:
    # exponential backoff with jitter
    if attempt < 1:
        attempt = 1
    r = rng or random
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = r.randint(0, min(30, exp // 3))
    return int(exp + jitter)


def _trim_error(msg: str, *, limit: int = 1500) -> str:
    msg = (msg or "").strip()
    if len(msg) <= limit:
        return msg
    return msg[:limit] + "…"


async def mark_started(
    db: AsyncSession,
    *,
    model,
    row_id: str,
    plan: RetryPlan,
    actor_id: str,
) -> None:
    values: dict[str, object] = {"updated_by": actor_id}


    if plan.started_at_col:
        values[plan.started_at_col] = func.now()

    if plan.error_col:
        values[plan.error_col] = None

    await db.execute(update(model).where(model.id == row_id).values(**values))


async def mark_success(
    db: AsyncSession,
    *,
    model,
    row_id: str,
    plan: RetryPlan,
    actor_id: str,
    normalized_at_col: str | None = None,
) -> None:
    values: dict[str, object] = {"updated_by": actor_id}
    if normalized_at_col:
        values[normalized_at_col] = func.now()

    values[plan.attempts_col] = 0
    values[plan.next_at_col] = None
    
    if plan.started_at_col:
        values[plan.started_at_col] = None
    if plan.error_col:
        values[plan.error_col] = None

    await db.execute(update(model).where(model.id == row_id).values(**values))



async def mark_failure(
    db: AsyncSession,
    *,
    model,
    row_id: str,
    plan: RetryPlan,
    actor_id: str,
    error_message: str,
    attempts_expr,
    attempt_after: int,
    base: int = 10,
    cap: int = 900,
    rng: random.Random | None = None,
) -> None:
    delay = compute_backoff_seconds(attempt_after, base=base, cap=cap, rng=rng)

    next_at = func.now() + timedelta(seconds=delay)

    values: dict[str, object] = {
        "updated_by": actor_id,
        plan.attempts_col: attempts_expr,
        plan.next_at_col: next_at,
    }
    if plan.started_at_col:
        values[plan.started_at_col] = None
    if plan.error_col:
        values[plan.error_col] = _trim_error(error_message)

    await db.execute(update(model).where(model.id == row_id).values(**values))