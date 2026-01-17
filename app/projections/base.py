from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.canonical.v1.listing import ListingCanonicalV1


@dataclass(frozen=True)
class ProjectionContext:
    tenant_id: str
    partner_id: str
    agent_id: str

    destination: str

    # External identities needed for destination payloads
    external_agent_id: str | None = None
    external_listing_id: str | None = None


@runtime_checkable
class ListingProjector(Protocol):
    """
    Maps canonical listing -> destination payload.
    """
    destination: str

    def project_listing(
        self,
        *,
        canonical: ListingCanonicalV1,
        ctx: ProjectionContext,
    ) -> dict[str, Any]:
        ...
