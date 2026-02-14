from __future__ import annotations

import copy
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_settings import PartnerSettings


# Single source of truth for defaults
DEFAULT_PARTNER_SETTINGS: dict[str, Any] = {
    "media": {
        "allow_external": True,
        "allowed_domains": [],
        "max_bytes": 20_000_000,
        "max_images": 50,
    },
    "rate_limit_per_minute": 60,
    "circuit_breaker_threshold": 5,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge override into base without mutating inputs.
    """
    result = copy.deepcopy(base)

    for k, v in (override or {}).items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v

    return result


def merge_with_defaults(config: dict | None) -> dict[str, Any]:
    """
    Always return a fully-populated config.
    """
    return _deep_merge(DEFAULT_PARTNER_SETTINGS, config or {})


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
        return copy.deepcopy(DEFAULT_PARTNER_SETTINGS)

    return merge_with_defaults(row.config)