from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Transport = Literal["push_api", "hosted_feed", "pull_only"]
AuthType = Literal["none", "api_key", "basic", "oauth2", "hmac", "custom"]


@dataclass(frozen=True)
class DestinationCapabilities:
    """
    Describes WHAT a destination can do and HOW we integrate.
    """
    destination: str
    transport: Transport
    auth: AuthType

    # delivery behavior hints
    supports_upsert: bool = True
    supports_delete: bool = False
    supports_media: bool = True

    # operational hints
    max_requests_per_minute: int | None = None
    max_payload_bytes: int | None = None
