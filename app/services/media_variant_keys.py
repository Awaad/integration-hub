from __future__ import annotations

def build_variant_storage_key(
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    media_id: str,
    version: str,
    variant: str,
    ext: str,
) -> str:
    variant = variant.strip().lower()
    version = version.strip().lower()
    ext = ext.strip().lower().lstrip(".")
    # tenant/partner/agent/media_id/variants/v1/thumb.webp
    return f"{tenant_id}/{partner_id}/{agent_id}/{media_id}/variants/{version}/{variant}.{ext}"
