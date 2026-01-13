from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.internal_admin import require_internal_admin
from app.services.outbox_dispatcher import dispatch_outbox

router = APIRouter()

@router.post("/internal/outbox/dispatch", dependencies=[Depends(require_internal_admin)])
async def internal_dispatch_outbox(db: AsyncSession = Depends(get_db)) -> dict:
    count = await dispatch_outbox(db, batch_size=100)
    return {"dispatched": count}
