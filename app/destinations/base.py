from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.destinations.capabilities import DestinationCapabilities


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None
    detail: dict[str, Any] | None = None
    external_id: str | None = None  # destination listing id, if returned


@runtime_checkable
class DestinationConnector(Protocol):
    """
    A connector handles transport & auth for a destination.
    It receives destination-specific payload (already projected).
    """

    destination: str

    def capabilities(self) -> DestinationCapabilities:
        ...

    async def publish_listing(
        self,
        *,
        payload: dict[str, Any],
        credentials: dict[str, Any],
    ) -> PublishResult:
        """
        Push API transport: do an upsert via HTTP.
        Hosted feed transport: feed builder runs elsewhere.
        Pull-only: may return ok=False with retryable=False.
        """
        ...

    async def delete_listing(
        self,
        *,
        external_listing_id: str,
        credentials: dict[str, Any],
    ) -> PublishResult:
        """
        Only if supports_delete.
        """
        ...
