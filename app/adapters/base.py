from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.canonical.v1.listing import ListingCanonicalV1


@dataclass(frozen=True)
class AdapterContext:
    """
    Optional context passed to adapters.
    Lets us include metadata needed for mapping without coupling to app models.
    """
    tenant_id: str
    partner_id: str
    agent_id: str | None
    # partner-scoped listing identifier if provided
    source_listing_id: str | None = None


@dataclass(frozen=True)
class AdapterResult:
    ok: bool
    canonical: dict[str, Any] | None
    errors: list[dict[str, Any]]


class PartnerAdapter(Protocol):
    """
    PartnerAdapter maps partner/source payload -> canonical.listing@1.0 dict.
    """
    partner_key: str

    def map_listing(
        self,
        *,
        payload: dict[str, Any],
        ctx: AdapterContext,
    ) -> AdapterResult:
        ...
