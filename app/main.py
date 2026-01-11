from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.telemetry import setup_telemetry

app = FastAPI(title="Hub API", version="0.1.0")

setup_telemetry(app)
app.include_router(v1_router)
