from fastapi import APIRouter, Depends, HTTPException
from app.adapters.registry import supported_adapters
from app.services.auth import Actor, require_partner_admin

router = APIRouter()

@router.get("/partners/{partner_id}/adapters", response_model=list[dict])
async def list_adapters(partner_id: str, actor: Actor = Depends(require_partner_admin)):
    if actor.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Cross-partner access forbidden")
    return supported_adapters()
