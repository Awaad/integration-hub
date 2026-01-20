from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog

async def audit(
    db: AsyncSession,
    *,
    tenant_id: str | None,
    partner_id: str | None,
    actor_api_key_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        partner_id=partner_id,
        actor_api_key_id=actor_api_key_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    ))
