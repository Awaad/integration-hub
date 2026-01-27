from dataclasses import dataclass
from typing import Protocol, Any

# EXCESSIVE MAYBE DELETE LATER AND RELY ON DESTINATIONS/BASE.PY
@dataclass(frozen=True)
class PublishResult:
    ok: bool
    external_id: str | None = None
    detail: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = True


class DestinationConnector(Protocol):
    key: str

    async def publish_listing(self, listing: dict, credentials: dict) -> PublishResult:
        ...
