from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.auth import Actor, require_partner_admin
from app.models.partner_destination_setting import PartnerDestinationSetting
from app.models.feed_snapshot import FeedSnapshot
from app.destinations.registry import get_destination_connector
from app.destinations.mapping_registry import get_mapping_plugin
from app.destinations.mapping_base import MappingKeySet
from app.canonical.v1.listing import ListingCanonicalV1
from app.models.listing import Listing
from app.services.partner_destination_config import ensure_feed_token

router = APIRouter()

@router.get("/partners/{partner_id}/destinations/{destination}/export-readiness")
async def export_readiness(
    partner_id: str,
    destination: str,
    include_import_templates: bool = Query(default=True),
    actor: Actor = Depends(require_partner_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")

    dest = destination.lower().strip()

    setting = (await db.execute(select(PartnerDestinationSetting).where(
        PartnerDestinationSetting.tenant_id == actor.tenant_id,
        PartnerDestinationSetting.partner_id == partner_id,
        PartnerDestinationSetting.destination == dest,
    ))).scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Destination not configured")

    if not setting.is_enabled:
        return {
            "destination": dest,
            "enabled": False,
            "reason": "Destination disabled",
        }

    # Capabilities
    try:
        connector = get_destination_connector(dest)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown destination: {dest}")

    caps = connector.capabilities()

    # Latest snapshot (for hosted feeds)
    latest = (await db.execute(
        select(FeedSnapshot).where(
            FeedSnapshot.tenant_id == actor.tenant_id,
            FeedSnapshot.partner_id == partner_id,
            FeedSnapshot.destination == dest,
        ).order_by(desc(FeedSnapshot.created_at)).limit(1)
    )).scalar_one_or_none()

    # Feed URL (only for hosted_feed)
    feed_url = None
    if caps.transport == "hosted_feed":
        token = await ensure_feed_token(db, tenant_id=actor.tenant_id, partner_id=partner_id, destination=dest)
        # commit not required here; but safe if ensure_feed_token mutated config
        await db.commit()
        feed_url = f"/v1/feeds/{partner_id}/{dest}.xml?token={token}"

    # Mapping diff via plugin (if plugin exists)
    missing = {"enums": {}, "geo": []}
    warnings = []
    import_templates = {}

    try:
        plugin = get_mapping_plugin(dest)
    except Exception:
        plugin = None

    if plugin:
        rows = (await db.execute(select(Listing).where(
            Listing.tenant_id == actor.tenant_id,
            Listing.partner_id == partner_id,
            Listing.schema == "canonical.listing",
            Listing.schema_version == "1.0",
        ))).scalars().all()

        agg_enum: dict[str, set[str]] = {}
        agg_geo: set[str] = set()

        for r in rows:
            can = ListingCanonicalV1.model_validate(r.payload)
            ks = plugin.required_mapping_keys(can)
            for ns, skeys in ks.enum_keys.items():
                agg_enum.setdefault(ns, set()).update(skeys)
            agg_geo |= set(ks.geo_keys)

        check = await plugin.check_mappings(
            db=db,
            tenant_id=actor.tenant_id,
            partner_id=partner_id,
            keys=MappingKeySet(enum_keys=agg_enum, geo_keys=agg_geo),
        )

        missing = {
            "enums": {ns: sorted(list(v)) for ns, v in check.missing.enum_keys.items()},
            "geo": sorted(list(check.missing.geo_keys)),
        }
        warnings = list(check.warnings or [])

        # provide import template payloads for ops (values empty)
        if include_import_templates:
            # enum templates
            enum_payloads = []
            for ns, keys in check.missing.enum_keys.items():
                clean = [k for k in keys if not str(k).startswith("<")]
                if not clean:
                    continue
                enum_payloads.append({
                    "destination": dest,
                    "namespace": ns,
                    "mappings": {k: "" for k in sorted(clean)},  # ops fills destination ids
                })

            # geo template (city:area -> destination_area_id)
            geo_map = {k: "" for k in sorted([g for g in check.missing.geo_keys if ":" in g])}

            import_templates = {
                "destination_enums": enum_payloads,
                "destination_areas": {
                    "destination": dest,
                    "country_code": "NCY",  # plugin can later expose this; for now it matches NCY strategy
                    "mappings": geo_map,
                } if geo_map else None,
            }

    return {
        "destination": dest,
        "enabled": True,
        "transport": caps.transport,
        "feed_url": feed_url,
        "latest_snapshot": None if not latest else {
            "created_at": latest.created_at.isoformat() if getattr(latest, "created_at", None) else None,
            "content_hash": latest.content_hash,
            "listing_count": latest.listing_count,
            "meta": latest.meta,
        },
        "missing_mappings": missing,
        "warnings": warnings,
        "import_templates": import_templates,
    }
