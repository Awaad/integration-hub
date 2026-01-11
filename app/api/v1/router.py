from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.partners import router as partners_router


router = APIRouter(prefix="/v1")
router.include_router(health_router, tags=["health"])
router.include_router(partners_router, tags=["partners"])