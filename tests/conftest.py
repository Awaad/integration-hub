import os
import asyncio
import pytest
import httpx

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event

# Import Base + all models so metadata is complete
from app.models.base import Base  # AuditMixin lives here
from app.models.tenant import Tenant  # noqa: F401
from app.models.partner import Partner  # noqa: F401
from app.models.agent import Agent  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.outbox import OutboxEvent  # noqa: F401
from app.models.agent_credential import AgentCredential  # noqa: F401
from app.models.listing import Listing  # noqa: F401
from app.models.idempotency import IdempotencyKey  # noqa: F401

from app.main import app
from app.core.db import get_db


def _test_db_url() -> str:
    url = os.getenv("DATABASE_URL_TEST")
    if not url:
        raise RuntimeError("DATABASE_URL_TEST is not set")
    return url


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(_test_db_url(), future=True, pool_pre_ping=True)
    try:
        # Create schema once per test session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """
    Transactional rollback per test:
    - Start an outer transaction
    - Start a nested transaction (SAVEPOINT)
    - Restart SAVEPOINT after each internal commit (SQLAlchemy pattern)
    """
    async with async_engine.connect() as conn:
        trans = await conn.begin()

        session_factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        session = session_factory()

        await session.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def _restart_savepoint(sess, transaction):
            # If the nested transaction ended, start a new one
            parent = getattr(transaction, "_parent", None)
            if transaction.nested and parent is not None and not parent.nested:
                sess.begin_nested()

        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def client(db_session: AsyncSession):
    """
    HTTP client that uses the test DB session via dependency override.
    """
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
