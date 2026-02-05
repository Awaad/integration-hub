from __future__ import annotations
from pydantic import BaseModel

class RotateMediaPublicTokenOut(BaseModel):
    partner_id: str
    scope: str
    token_id: str
    public_token: str | None = None
    token_prefix: str
