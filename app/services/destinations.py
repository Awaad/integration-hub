from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_destination_setting import PartnerDestinationSetting

async def get_enabled_destinations_for_partner(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
) -> set[str]:
    rows = (await db.execute(select(PartnerDestinationSetting.destination).where(
        PartnerDestinationSetting.tenant_id == tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.is_enabled.is_(True),
    ))).scalars().all()
    return set(rows)
