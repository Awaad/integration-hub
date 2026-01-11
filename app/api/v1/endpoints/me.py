from fastapi import APIRouter, Depends

from app.schemas.me import MeOut
from app.services.auth import Actor, get_actor

router = APIRouter()

@router.get("/me", response_model=MeOut)
async def me(actor: Actor = Depends(get_actor)) -> MeOut:
    return MeOut(
        api_key_id=actor.api_key_id,
        tenant_id=actor.tenant_id,
        partner_id=actor.partner_id,
        role=actor.role,
        agent_id=actor.agent_id,
    )
