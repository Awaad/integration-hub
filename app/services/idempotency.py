import hashlib
import json
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey
from app.services.auth import Actor


def _hash_request(path: str, body: dict) -> str:
    # Stable hash to detect conflicts (same idempotency key but different request)
    raw = json.dumps({"path": path, "body": body}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


async def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key header")
    if len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key too long")
    return idempotency_key


async def get_or_reserve_idempotency(
    *,
    db: AsyncSession,
    actor: Actor,
    idempotency_key: str,
    request_path: str,
    request_body: dict,
) -> tuple[IdempotencyKey | None, str]:
    """
    Returns:
      (existing_record, request_hash)
    If existing_record is not None => you should return existing_record.response immediately.
    """
    req_hash = _hash_request(request_path, request_body)

    stmt = select(IdempotencyKey).where(
        IdempotencyKey.tenant_id == actor.tenant_id,
        IdempotencyKey.key == idempotency_key,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        if existing.request_hash != req_hash:
            raise HTTPException(status_code=409, detail="Idempotency-Key reuse with different request")
        return existing, req_hash

    # Reserve by inserting an empty response row
    row = IdempotencyKey(
        tenant_id=actor.tenant_id,
        partner_id=actor.partner_id,
        actor_api_key_id=actor.api_key_id,
        key=idempotency_key,
        request_hash=req_hash,
        response={},
    )
    db.add(row)
    # Flush so it becomes visible in this transaction (unique constraint enforced)
    await db.flush()
    return None, req_hash


async def store_idempotency_response(
    *,
    db: AsyncSession,
    actor: Actor,
    idempotency_key: str,
    response: dict,
) -> None:
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.tenant_id == actor.tenant_id,
        IdempotencyKey.key == idempotency_key,
    )
    row = (await db.execute(stmt)).scalar_one()
    row.response = response
    await db.flush()
