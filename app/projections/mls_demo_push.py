from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.canonical.v1.listing import ListingCanonicalV1
from app.projections.base import ProjectionContext
from app.destinations.mls_demo_push.projection import project_mls_demo_push


@dataclass(frozen=True)
class MlsDemoPushProjector:
    destination: str = "mls_demo_push"

    def project_listing(
        self,
        *,
        canonical: ListingCanonicalV1,
        ctx: ProjectionContext,
    ) -> dict[str, Any]:
        res = project_mls_demo_push(
            canonical=canonical,
            external_listing_id=ctx.external_listing_id,
            mapped=None,
        )

        if not res.ok or not res.payload:
            # worker semantics: projection failure should bubble and mark delivery failed.
            raise ValueError({
                "errors": [{"code": e.code, "message": e.message} for e in res.errors],
                "warnings": [{"code": w.code, "message": w.message} for w in res.warnings],
            })

        # attach warnings for observability
        if res.warnings:
            res.payload["_warnings"] = [{"code": w.code, "message": w.message} for w in res.warnings]

        return res.payload
