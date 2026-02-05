from fastapi import APIRouter
from app.api.public.endpoints.media import router as public_media_router

router = APIRouter(prefix="/public")
router.include_router(public_media_router, tags=["public-media"])