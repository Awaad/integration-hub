import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.base import Base
from app.models.tenant import Tenant  # noqa: F401
from app.models.partner import Partner  # noqa: F401
from app.models.agent import Agent  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.outbox import OutboxEvent  # noqa: F401
from app.models.agent_credential import AgentCredential  # noqa: F401
from app.models.listing import Listing  # noqa: F401
from app.models.idempotency import IdempotencyKey  # noqa: F401
from app.models.delivery import Delivery, DeliveryAttempt  # noqa: F401


config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
