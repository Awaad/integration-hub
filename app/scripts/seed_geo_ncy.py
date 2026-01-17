import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.geo_country import GeoCountry

async def main():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        existing = (await db.execute(select(GeoCountry).where(GeoCountry.code == "NCY"))).scalar_one_or_none()
        if not existing:
            db.add(GeoCountry(code="NCY", name="North Cyprus"))
            await db.commit()
            print("Inserted NCY")
        else:
            print("NCY already exists")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
# This script seeds the database with the country code "NCY" for North Cyprus if it doesn't already exist.