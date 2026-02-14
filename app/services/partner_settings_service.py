from __future__ import annotations

import copy
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_settings import PartnerSettings


DEFAULT_MEDIA_POLICY = {
    "media_ingest": {
        "allow_external": False,
        "allowed_domains": [],
        "max_per_minute": 60,
    }
}

def _merge_policy(config: dict) -> dict:
    merged = copy.deepcopy(DEFAULT_MEDIA_POLICY)
    for k, v in (config or {}).items():
        if isinstance(v, dict) and k in merged:
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


async def get_partner_settings(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(PartnerSettings).where(
                PartnerSettings.tenant_id == tenant_id,
                PartnerSettings.partner_id == partner_id,
            )
        )
    ).scalar_one_or_none()

    if not row:
        return copy.deepcopy(DEFAULT_MEDIA_POLICY)

    return _merge_policy(row.config)