import os
import pytest
from sqlalchemy import select, func

from app.models.outbox import OutboxEvent

@pytest.mark.asyncio
async def test_e2e_bootstrap_create_agent_rotate_and_upsert_listing(client, db_session):
    # 1) bootstrap partner (requires internal admin)
    internal_key = os.getenv("INTERNAL_ADMIN_KEY", "test-internal")
    r = await client.post(
        "/v1/partners/bootstrap",
        headers={"X-Internal-Admin-Key": internal_key},
        json={"tenant_name": "Tenant T", "partner_name": "Partner P"},
    )
    assert r.status_code in (200, 201), r.text
    boot = r.json()
    partner_id = boot["partner_id"]
    partner_admin_key = boot["partner_admin_api_key"]

    # 2) create agent (requires partner_admin)
    r = await client.post(
        f"/v1/partners/{partner_id}/agents",
        headers={"X-API-Key": partner_admin_key},
        json={
            "email": "agent1@partner.com",
            "display_name": "Agent 1",
            "rules": {"allowed_destinations": ["mls_a"]},
        },
    )
    assert r.status_code == 200, r.text
    agent = r.json()
    agent_id = agent["id"]

    # 3) rotate agent api key (requires partner_admin)
    r = await client.post(
        f"/v1/partners/{partner_id}/agents/{agent_id}/api-keys/rotate",
        headers={"X-API-Key": partner_admin_key},
    )
    assert r.status_code == 200, r.text
    rotated = r.json()
    agent_api_key = rotated["plain_key"]

    # 4) upsert listing (requires agent key)
    listing_body = {
        "status": "draft",
        "schema": "canonical.listing.v1",
        "schema_version": "1.0.0",
        "payload": {
            "title": "2BR Apartment",
            "pricing": {"currency": "EUR", "amount": 250000},
            "location": {"country": "CY"},
        },
    }
    headers = {
        "X-API-Key": agent_api_key,
        "Idempotency-Key": "upsert-L-1001-v1",
    }

    url = f"/v1/partners/{partner_id}/agents/{agent_id}/listings/L-1001"
    r1 = await client.put(url, headers=headers, json=listing_body)
    assert r1.status_code == 200, r1.text
    first = r1.json()

    # retry with same idempotency key -> same response
    r2 = await client.put(url, headers=headers, json=listing_body)
    assert r2.status_code == 200, r2.text
    second = r2.json()

    assert second["id"] == first["id"]
    assert second["content_hash"] == first["content_hash"]

    # verify outbox only has one event (idempotent)
    outbox_count = (
        await db_session.execute(select(func.count()).select_from(OutboxEvent))
    ).scalar_one()
    assert outbox_count == 1
