from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.partners import router as partners_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.me import router as me_router


router = APIRouter(prefix="/v1")
router.include_router(health_router, tags=["health"])
router.include_router(partners_router, tags=["partners"])
router.include_router(agents_router, tags=["agents"])
router.include_router(me_router, tags=["me"])