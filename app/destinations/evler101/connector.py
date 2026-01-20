from __future__ import annotations

from app.destinations.capabilities import DestinationCapabilities
from app.destinations.base import DestinationConnector, PublishResult


class Evler101HostedFeedConnector(DestinationConnector):
    """
    101evler is a hosted XML feed import destination.

    Implementation note (later):
    - Generate an XML feed with <ads><ad>...</ad></ads>
    - <ad_key> must be unique and stable; updates require newer <lastupdate>.
    - Photos are deduped by URL; to change photos you must send new URLs.
    See: 101evler XML Import documentation. :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}
    """

    destination = "101evler"

    def capabilities(self) -> DestinationCapabilities:
        return DestinationCapabilities(
            destination=self.destination,
            transport="hosted_feed",
            supports_delete=False,      # not specified yet
            supports_media=True,        # feed supports <ad_pictures> :contentReference[oaicite:7]{index=7}
            features={"timed_offers": False},
            listing_inclusion_policy="exclude_inactive",
        )

    async def publish_listing(self, *, payload: dict, credentials: dict) -> PublishResult:
        """
        Hosted-feed destinations are NOT per-listing push; publishing is done by feed snapshots.
        So this method is intentionally a no-op success to keep the delivery pipeline consistent.

        The actual work happens in the feed dispatcher which builds and hosts the feed artifact.
        """
        return PublishResult(ok=True, retryable=False, detail={"mode": "hosted_feed_noop"})
