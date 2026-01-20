from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

Transport = Literal["push_api", "hosted_feed", "pull_only"]
AuthType = Literal["none", "api_key", "basic", "oauth2", "hmac", "custom"]


ListingInclusionPolicy = Literal["exclude_inactive", "include_with_status"]

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

    features: dict[str, bool] = field(default_factory=dict)

    listing_inclusion_policy: ListingInclusionPolicy = "exclude_inactive"
    # operational hints
    max_requests_per_minute: int | None = None
    max_payload_bytes: int | None = None
