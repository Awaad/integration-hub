from pydantic import BaseModel, Field, field_validator
from typing import List


class MediaPolicyConfig(BaseModel):
    allow_external: bool = True
    allowed_domains: List[str] = Field(default_factory=list)
    max_bytes: int = 20_000_000
    max_images: int = 50

    @field_validator("allowed_domains")
    @classmethod
    def normalize_domains(cls, v: List[str]) -> List[str]:
        return [d.lower().strip() for d in v if d]


class PartnerSettingsPayload(BaseModel):
    media: MediaPolicyConfig = Field(default_factory=MediaPolicyConfig)
    rate_limit_per_minute: int = 60
    circuit_breaker_threshold: int = 5

    model_config = {
        "extra": "forbid"
    }