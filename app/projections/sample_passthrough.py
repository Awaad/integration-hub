from __future__ import annotations

from app.canonical.v1.listing import ListingCanonicalV1
from app.projections.base import ListingProjector, ProjectionContext


class PassthroughProjector:
    """
    For destinations that accept canonical directly.
    """
    destination = "passthrough"

    def project_listing(self, *, canonical: ListingCanonicalV1, ctx: ProjectionContext) -> dict:
        data = canonical.model_dump(mode="json", exclude_none=True)
        
        if ctx.external_agent_id:
            data["agent_external_id"] = ctx.external_agent_id
        if ctx.external_listing_id:
            data["external_listing_id"] = ctx.external_listing_id
        return data
