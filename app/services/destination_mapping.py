from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.destination_enum_mapping import DestinationEnumMapping

async def resolve_dest_enum(
    db: AsyncSession,
    *,
    destination: str,
    namespace: str,
    source_key: str,
) -> str | None:
    row = (await db.execute(select(DestinationEnumMapping.destination_value).where(
        DestinationEnumMapping.destination == destination,
        DestinationEnumMapping.namespace == namespace,
        DestinationEnumMapping.source_key == source_key,
    ))).scalar_one_or_none()
    return row
