from __future__ import annotations

from typing import Any

from app.adapters.base import AdapterContext, AdapterResult
from app.services.canonical_validate import validate_and_normalize_canonical


class PassthroughAdapter:
    """
    Assumes payload is already canonical.listing@1.0 (or close).
    Validates + normalizes and returns canonical dict.
    """
    partner_key = "passthrough"

    def map_listing(self, *, payload: dict[str, Any], ctx: AdapterContext) -> AdapterResult:
        # Ensure schema markers exist (helpful for sources that omit them)
        enriched: dict[str, Any] = dict(payload)
        enriched.setdefault("schema", "canonical.listing")
        enriched.setdefault("schema_version", "1.0")

        # Optionally inject ids if not present
        if "canonical_id" not in enriched and ctx.source_listing_id:
            enriched["canonical_id"] = ctx.source_listing_id

        res = validate_and_normalize_canonical(
            schema=enriched.get("schema", "canonical.listing"),
            schema_version=enriched.get("schema_version", "1.0"),
            payload=enriched,
        )

        if not res.ok:
            return AdapterResult(ok=False, canonical=None, errors=res.errors)

        return AdapterResult(ok=True, canonical=res.normalized, errors=[])
