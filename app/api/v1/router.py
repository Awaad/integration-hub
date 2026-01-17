from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.partners import router as partners_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.me import router as me_router
from app.api.v1.endpoints.credentials import router as credentials_router
from app.api.v1.endpoints.listings import router as listings_router
from app.api.v1.endpoints.internal import router as internal_router
from app.api.v1.endpoints.deliveries import router as deliveries_router
from app.api.v1.endpoints.ingest import router as ingest_router
from app.api.v1.endpoints.ingest_runs import router as ingest_runs_router
from app.api.v1.endpoints.adapter_preview import router as adapter_preview_router
from app.api.v1.endpoints.ingest_replay import router as ingest_replay_router
from app.api.v1.endpoints.partner_destinations import router as partner_dest_router
from app.api.v1.endpoints.feeds import router as feeds_router


router = APIRouter(prefix="/v1")
router.include_router(health_router, tags=["health"])
router.include_router(partners_router, tags=["partners"])
router.include_router(agents_router, tags=["agents"])
router.include_router(me_router, tags=["me"])
router.include_router(credentials_router, tags=["credentials"])
router.include_router(listings_router, tags=["listings"])
router.include_router(internal_router, tags=["internal"])
router.include_router(deliveries_router, tags=["deliveries"])
router.include_router(ingest_router, tags=["ingest"])
router.include_router(ingest_runs_router, tags=["ingest_runs"])
router.include_router(adapter_preview_router, tags=["adapter_preview"]) 
router.include_router(ingest_replay_router, tags=["ingest-replay"])
router.include_router(partner_dest_router, tags=["partner-destinations"])
router.include_router(feeds_router, tags=["feeds"])