import pytest
from sqlalchemy import select, func

from app.models.outbox import OutboxEvent

@pytest.mark.asyncio
async def test_upsert_listing_idempotent_creates_one_outbox(client, db_session, seed_agent):
    partner_id = seed_agent["partner_id"]
    agent_id = seed_agent["agent_id"]
    agent_api_key = seed_agent["agent_api_key"]

    url = f"/v1/partners/{partner_id}/agents/{agent_id}/listings/L-1001"

    headers = {
        "X-API-Key": agent_api_key,
        "Idempotency-Key": "upsert-L-1001-v1",
    }

    body = {
        "status": "draft",
        "schema": "canonical.listing.v1",
        "schema_version": "1.0.0",
        "payload": {
            "title": "2BR Apartment",
            "pricing": {"currency": "EUR", "amount": 250000},
            "location": {"country": "CY"},
        },
    }

    r1 = await client.put(url, json=body, headers=headers)
    assert r1.status_code == 200
    first = r1.json()

    r2 = await client.put(url, json=body, headers=headers)
    assert r2.status_code == 200
    second = r2.json()

    assert second["id"] == first["id"]
    assert second["content_hash"] == first["content_hash"]

    outbox_count = (
        await db_session.execute(select(func.count()).select_from(OutboxEvent))
    ).scalar_one()
    assert outbox_count == 1
