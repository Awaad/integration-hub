from __future__ import annotations
import secrets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_destination_setting import PartnerDestinationSetting


async def ensure_feed_token(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    destination: str,
) -> str:
    row = (await db.execute(
        select(PartnerDestinationSetting).where(
            PartnerDestinationSetting.tenant_id == tenant_id,
            PartnerDestinationSetting.partner_id == partner_id,
            PartnerDestinationSetting.destination == destination,
        )
    )).scalar_one_or_none()

    if not row:
        raise ValueError("PartnerDestinationSetting not found")

    cfg = dict(row.config or {})
    if cfg.get("feed_token"):
        return str(cfg["feed_token"])

    token = secrets.token_urlsafe(24)
    cfg["feed_token"] = token
    row.config = cfg
    await db.flush()
    return token
