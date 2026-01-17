from __future__ import annotations
from typing import Any

from app.destinations.capabilities import DestinationCapabilities
from app.destinations.registry import DestinationConnector, PublishResult


class PassthroughDestinationConnector:
    destination = "passthrough"

    def capabilities(self) -> DestinationCapabilities:
        return DestinationCapabilities(
            destination=self.destination,
            transport="push_api",
            auth="none",
            supports_delete=False,
        )

    async def publish_listing(self, *, payload: dict[str, Any], credentials: dict[str, Any]) -> PublishResult:
        # This is a no-op connector for smoke tests.
        return PublishResult(ok=True, retryable=False, detail={"noop": True}, external_id=payload.get("canonical_id"))

    async def delete_listing(self, *, external_listing_id: str, credentials: dict[str, Any]) -> PublishResult:
        return PublishResult(ok=False, retryable=False, error_code="NOT_SUPPORTED", error_message="delete not supported")
