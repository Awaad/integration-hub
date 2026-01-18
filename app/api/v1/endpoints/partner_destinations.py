from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.schemas.partner_destination import PartnerDestinationUpsert, PartnerDestinationOut
from app.services.auth import Actor, require_partner_admin
from app.destinations.registry import supported_destinations
from app.services.redaction import redact_payload


router = APIRouter()

_REDACT_EXTRA_KEYS = {"feed_token"}  # redact_payload is exact-match; "token" does not cover "feed_token"

def _redact_cfg(cfg):
    return redact_payload(cfg, extra_keys=_REDACT_EXTRA_KEYS)

@router.get("/partners/{partner_id}/destinations", response_model=list[PartnerDestinationOut])
async def list_partner_destinations(
    partner_id: str,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    rows = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
    ).order_by(PartnerDestinationSetting.destination.asc()))).scalars().all()

    return [
        PartnerDestinationOut(
            destination=r.destination,
            is_enabled=r.is_enabled,
            config=r.config,
            created_by=r.created_by,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.put("/partners/{partner_id}/destinations/{destination}", response_model=PartnerDestinationOut)
async def upsert_partner_destination(
    partner_id: str,
    destination: str,
    body: PartnerDestinationUpsert,
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest_norm = destination.lower().strip()

    # enforce destination exists in registry
    if dest_norm not in supported_destinations():
        raise HTTPException(status_code=404, detail=f"Unknown destination: {dest_norm}")
    

    insert_stmt = insert(PartnerDestinationSetting).values(
        tenant_id=actor.tenant_id,
        partner_id=partner_id,
        destination=dest_norm,
        is_enabled=body.is_enabled,
        # For a brand-new row, if config omitted, store {}.
        config=(body.config if body.config is not None else {}),
        created_by=actor.api_key_id,
        updated_by=actor.api_key_id,
    )

    # Postgres JSONB existence operator '?'
    excluded_cfg = insert_stmt.excluded.config
    existing_cfg = PartnerDestinationSetting.config

    excluded_has_feed = excluded_cfg.op("?")("feed_token")
    existing_has_feed = existing_cfg.op("?")("feed_token")

    # If body.config is None: keep existing config (no overwrite)
    # Else: use incoming config, but if incoming lacks feed_token and existing has it, copy it over
    cfg_when_override = case(
        # incoming explicitly includes feed_token -> trust it (supports rotate or clear)
        (excluded_has_feed, excluded_cfg),
        # incoming omits feed_token but existing has it -> preserve existing token
        (existing_has_feed, existing_cfg.op("||")(excluded_cfg)),
        # otherwise just use incoming
        else_=excluded_cfg,
    )

    config_expr = case(
        (excluded_cfg.is_(None), existing_cfg),
        else_=cfg_when_override,
    )


    stmt = (
        insert_stmt.on_conflict_do_update(
            constraint="uq_partner_destination",
            set_={
                "is_enabled": body.is_enabled,
                "config": config_expr,
                "updated_by": actor.api_key_id,
            },
        )
        .returning(PartnerDestinationSetting)
    )

    row = (await db.execute(stmt)).scalar_one()
    await db.commit()

    return PartnerDestinationOut(
        destination=row.destination,
        is_enabled=row.is_enabled,
        config=_redact_cfg(row.config),
        created_by=row.created_by,
        updated_by=row.updated_by,
    )
