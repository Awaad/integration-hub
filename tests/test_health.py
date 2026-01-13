import pytest
import httpx
from app.main import app

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
