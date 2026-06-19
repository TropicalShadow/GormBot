from logging import Logger, getLogger
from coghotswap import Watcher
from discord import Intents, __version__
from discord.bot import Bot
import logging
from os import getenv

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from db import DatabaseManager


class GormBot(Bot):
    logger: Logger = getLogger("GormBot")

    def __init__(self):
        super().__init__(intents=Intents.all(), debug_guilds=[1515413540972789790])
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        self.logger.addHandler(handler)
        self.logger.propagate = False
        self.logger.info("Discord Version: %s", __version__)
        self.logger.info("GormBot is initializing...")
        self.watcher = Watcher(self, "modules", preload=True)  # type: ignore

        self.setup_database()

    def setup_database(self) -> None:
        db_url = getenv("DB_URL")
        if db_url is None:
            raise ValueError("DB_URL environment variable is not set")

        self.engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self.db = DatabaseManager(self, self.session_factory)

    async def on_ready(self):
        self.logger.info("GormBot is ready!")

        if not self.user:
            return

        self.logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
