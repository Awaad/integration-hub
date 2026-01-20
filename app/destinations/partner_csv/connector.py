from __future__ import annotations
from app.destinations.base import DestinationConnector, PublishResult
from app.destinations.capabilities import DestinationCapabilities

class PartnerCSVHostedFeedConnector(DestinationConnector):
    destination = "partner_csv"

    def capabilities(self) -> DestinationCapabilities:
        return DestinationCapabilities(
            destination=self.destination,
            transport="hosted_feed",
            supports_delete=False,
            supports_media=False,
            listing_inclusion_policy="include_with_status",
        )

    async def publish_listing(self, *, payload: dict, credentials: dict) -> PublishResult:
        # hosted feed destinations are snapshot-based; no per-listing push
        return PublishResult(ok=True, retryable=False, detail={"mode": "hosted_feed_noop"})
