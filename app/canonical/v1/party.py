from pydantic import BaseModel, Field, EmailStr
from typing import Literal


class PartyV1(BaseModel):
    """
    Canonical party/actor representation.
    Used for agent, owner, developer, etc (KYC later plugs here).
    """
    id: str = Field(min_length=1, max_length=80)
    role: Literal["agent", "owner", "developer", "agency"] = "agent"

    display_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

    # Destination-specific identity hints (not secrets)
    external_ids: dict[str, str] = Field(
        default_factory=dict,
        description="Map of destination->external_id (optional hints; source of truth is agent_external_identities table).",
    )
