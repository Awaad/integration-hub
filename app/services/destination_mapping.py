from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Iterable

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

# bulk load (1 query per namespace, or 1 query for many namespaces)
async def load_dest_enum_map(
    db: AsyncSession,
    *,
    destination: str,
    namespace: str,
) -> dict[str, str]:
    rows = (
        await db.execute(
            select(DestinationEnumMapping.source_key, DestinationEnumMapping.destination_value).where(
                DestinationEnumMapping.destination == destination,
                DestinationEnumMapping.namespace == namespace,
            )
        )
    ).all()
    return {sk: dv for (sk, dv) in rows if sk is not None and dv is not None}


async def load_dest_enum_maps(
    db: AsyncSession,
    *,
    destination: str,
    namespaces: Iterable[str],
) -> dict[str, dict[str, str]]:
    ns_list = list(namespaces)
    if not ns_list:
        return {}

    rows = (
        await db.execute(
            select(
                DestinationEnumMapping.namespace,
                DestinationEnumMapping.source_key,
                DestinationEnumMapping.destination_value,
            ).where(
                DestinationEnumMapping.destination == destination,
                DestinationEnumMapping.namespace.in_(ns_list),
            )
        )
    ).all()

    out: dict[str, dict[str, str]] = {ns: {} for ns in ns_list}
    for ns, sk, dv in rows:
        if ns and sk and dv is not None:
            out.setdefault(ns, {})[sk] = dv
    return out


# ---- New: pure resolution helpers (no DB calls) ----
def resolve_enum_with_fallback(
    *,
    source_key: str | None,
    db_map: dict[str, str],
    cfg_map: dict[str, str],
) -> tuple[str | None, str | None]:
    """
    Returns (destination_value, source)
      source in {"db", "config_fallback", None}
    """
    if not source_key:
        return None, None

    v = db_map.get(source_key)
    if v is not None:
        return v, "db"

    v = cfg_map.get(source_key)
    if v is not None:
        return v, "config_fallback"

    return None, None