from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any

from sqlalchemy.ext.asyncio import AsyncSession

@dataclass(frozen=True)
class FeedBuildOutput:
    format: str               # "xml" / "csv"
    bytes: bytes
    listing_count: int
    meta: dict[str, Any]
    content_hash: str

class HostedFeedPlugin(Protocol):
    destination: str
    format: str  # "xml" | "csv" |

    async def build(
        self,
        *,
        db: AsyncSession,
        tenant_id: str,
        partner_id: str,
        config: dict[str, Any],
    ) -> FeedBuildOutput:
        ...
