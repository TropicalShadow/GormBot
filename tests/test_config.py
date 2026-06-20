import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.DatabaseSchema import Base, BotConfig
from db.ConfigConnection import ConfigConnection


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_and_get_config(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    result = await conn.get("stripe_enabled")
    assert result == "true"


@pytest.mark.asyncio
async def test_get_missing_returns_none(session):
    conn = ConfigConnection(session)
    result = await conn.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_set_overwrites(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    await conn.set("stripe_enabled", "false")
    result = await conn.get("stripe_enabled")
    assert result == "false"


@pytest.mark.asyncio
async def test_get_all(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    await conn.set("crypto_enabled", "false")
    result = await conn.get_all()
    assert result == {"stripe_enabled": "true", "crypto_enabled": "false"}
