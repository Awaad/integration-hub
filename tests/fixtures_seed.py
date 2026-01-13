import pytest
import pytest_asyncio
from app.core.ids import gen_id
from app.core.security import generate_api_key
from app.models.tenant import Tenant
from app.models.partner import Partner
from app.models.agent import Agent
from app.models.api_key import ApiKey

@pytest_asyncio.fixture
async def seed_partner_admin(db_session):
    tenant_id = gen_id("tnt")
    partner_id = gen_id("prt")

    tenant = Tenant(id=tenant_id, name="Tenant Test", created_by="test", updated_by="test")
    partner = Partner(id=partner_id, tenant_id=tenant_id, name="Partner Test", created_by="test", updated_by="test")

    db_session.add_all([tenant, partner])
    await db_session.flush()

    admin_key = generate_api_key()
    key_row = ApiKey(
        tenant_id=tenant_id,
        partner_id=partner_id,
        role="partner_admin",
        agent_id=None,
        key_prefix=admin_key.prefix,
        key_hash=admin_key.hashed,
        is_active=True,
        created_by="test",
        updated_by="test",
    )

    db_session.add(key_row)
    await db_session.flush()

    return {
        "tenant_id": tenant_id,
        "partner_id": partner_id,
        "plain_key": admin_key.plain,
        "api_key_id": key_row.id,
    }


@pytest.fixture
async def seed_agent(db_session, seed_partner_admin):
    tenant_id = seed_partner_admin["tenant_id"]
    partner_id = seed_partner_admin["partner_id"]

    agent_id = gen_id("agt")
    agent = Agent(
        id=agent_id,
        tenant_id=tenant_id,
        partner_id=partner_id,
        email="agent@test.com",
        display_name="Agent Test",
        rules={"allowed_destinations": ["mls_a"]},
        created_by="test",
        updated_by="test",
    )
    db_session.add(agent)
    await db_session.flush()

    agent_key = generate_api_key()
    agent_key_row = ApiKey(
        tenant_id=tenant_id,
        partner_id=partner_id,
        role="agent",
        agent_id=agent_id,
        key_prefix=agent_key.prefix,
        key_hash=agent_key.hashed,
        is_active=True,
        created_by="test",
        updated_by="test",
    )
    db_session.add(agent_key_row)
    await db_session.flush()

    return {
        **seed_partner_admin,
        "agent_id": agent_id,
        "agent_api_key": agent_key.plain,
        "agent_api_key_id": agent_key_row.id,
    }
