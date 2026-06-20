from typing import TYPE_CHECKING
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .TicketConnection import TicketConnection
from .CommissionConnection import CommissionConnection
from .ConfigConnection import ConfigConnection
from .DatabaseSchema import Base


if TYPE_CHECKING:
    from utils import GormBot


class DatabaseManager:
    def __init__(self, bot: "GormBot", session_factory: async_sessionmaker[AsyncSession]):
        self.bot = bot
        self.session_factory = session_factory

    @asynccontextmanager
    async def ticket_session(self):
        async with self.session_factory() as session:
            yield TicketConnection(session)

    @asynccontextmanager
    async def commission_session(self):
        async with self.session_factory() as session:
            yield CommissionConnection(session)

    @asynccontextmanager
    async def config_session(self):
        async with self.session_factory() as session:
            yield ConfigConnection(session)

    async def create_tables(self, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
