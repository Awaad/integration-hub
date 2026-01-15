from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.canonical.v1.media import MediaV1
from app.canonical.v1.party import PartyV1


# --- Optional ISO 4217 validation (only if pycountry is installed) ---
def _load_iso4217() -> set[str] | None:
    try:
        import pycountry  # type: ignore
        return {c.alpha_3 for c in pycountry.currencies}
    except Exception:
        return None


_ISO4217: set[str] | None = _load_iso4217()


class MoneyV1(BaseModel):
    currency: str = Field(default="GBP", min_length=3, max_length=3)
    amount: int = Field(ge=0, description="Amount in minor units (e.g., cents).")

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        v2 = v.strip().upper()
        if len(v2) != 3:
            raise ValueError("currency must be a 3-letter code")
        # membership check
        if _ISO4217 is not None and v2 not in _ISO4217:
            raise ValueError(f"currency '{v2}' is not a valid ISO 4217 code")
        return v2


class PriceRuleV1(BaseModel):
    """
    Supports timed offers, scheduled price changes, etc.
    """
    kind: Literal["fixed", "timed_offer"] = "fixed"
    price: MoneyV1
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_rule(self) -> "PriceRuleV1":
        if self.kind == "timed_offer":
            if self.starts_at is None or self.ends_at is None:
                raise ValueError("timed_offer requires starts_at and ends_at")
            if self.starts_at >= self.ends_at:
                raise ValueError("timed_offer requires starts_at < ends_at")
        return self


class AddressV1(BaseModel):
    line1: str | None = Field(default=None, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    area: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=2, description="ISO 3166-1 alpha-2 if known")
    lat: float | None = None
    lng: float | None = None

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < -90.0 or v > 90.0:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < -180.0 or v > 180.0:
            raise ValueError("lng must be between -180 and 180")
        return v


class PropertyV1(BaseModel):
    """
    Property facts (expanded).

    - category is a stable coarse bucket for destination mapping
    - subtype captures high-variance values (penthouse, duplex, full_building, etc.)
    - construction_status covers existing / under construction / off plan
    """
    category: Literal["apartment", "house", "villa", "land", "commercial", "other"] = "other"
    subtype: str | None = Field(
        default=None,
        max_length=80,
        description="High-variance subtype (e.g., penthouse, duplex, full_building, studio, shop, office).",
    )

    # Property-level title/description (distinct from listing title/description)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)

    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    area_m2: int | None = Field(default=None, ge=0)
    lot_m2: int | None = Field(default=None, ge=0)

    construction_status: Literal["existing", "under_construction", "off_plan"] = "existing"
    year_built: int | None = Field(default=None, ge=1600, le=3000)
    completion_year: int | None = Field(default=None, ge=1600, le=3000)

    @model_validator(mode="after")
    def validate_construction(self) -> "PropertyV1":
        # If it's not yet built, completion_year is more relevant than year_built.
        if self.construction_status in ("under_construction", "off_plan"):
            if self.completion_year is None:
                raise ValueError("completion_year is required for under_construction/off_plan")
        return self


class RentV1(BaseModel):
    """
    Rent-specific pricing block.
    """
    price: MoneyV1
    period: Literal["day", "week", "month", "year"] = "month"
    deposit: MoneyV1 | None = None


class ListingCanonicalV1(BaseModel):
    """
    Canonical Listing v1.

    This is the stable contract that inbound adapters output and outbound projections consume.
    """
    schema: Literal["canonical.listing"] = "canonical.listing"
    schema_version: Literal["1.0"] = "1.0"

    # Stable canonical identifiers
    canonical_id: str = Field(min_length=1, max_length=80, description="Hub canonical listing id (listing.id).")
    source_listing_id: str | None = Field(
        default=None,
        max_length=120,
        description="Partner/source-native listing id (optional; used for ingest endpoints).",
    )

    status: Literal["draft", "active", "pending", "sold", "withdrawn"] = "draft"

    purpose: Literal["sale", "rent"] = "sale"

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)

    address: AddressV1 = Field(default_factory=AddressV1)
    property: PropertyV1 = Field(default_factory=PropertyV1)

    # Pricing: base + optional schedule
    # - For sale: list_price is the main price
    # - For rent: prefer rent block, but list_price may still be used by some sources
    list_price: MoneyV1 | None = None
    rent: RentV1 | None = None
    pricing_rules: list[PriceRuleV1] = Field(default_factory=list)

    # Parties
    agent: PartyV1 | None = None
    owner: PartyV1 | None = None

    # Media
    media: list[MediaV1] = Field(default_factory=list)

    # Extra fields that are still canonical but not yet modeled strictly
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible attributes (amenities, energy rating, etc).",
    )

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "ListingCanonicalV1":
        # Stable ordering for hashing/idempotency
        self.media.sort(key=lambda m: (m.order, m.id))

        # Basic purpose/pricing consistency
        if self.purpose == "rent":
            if self.rent is None and self.list_price is None:
                raise ValueError("purpose='rent' requires rent or list_price")
        return self
