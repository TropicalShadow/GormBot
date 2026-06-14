from logging import Logger, getLogger
from coghotswap import Watcher
from discord import Intents, __version__
from discord.bot import Bot

from db import DatabaseManager


class GormBot(Bot):
    logger: Logger = getLogger("GormBot")

    def __init__(self, token: str):
        super().__init__(token=token, intents=Intents.all(), debug_guilds=[1515413540972789790])
        self.logger.info("Discord Version: %s", __version__)
        self.logger.info("GormBot is initializing...")
        self.watcher = Watcher(self, "modules", preload=True)  # type: ignore
        self.db = DatabaseManager(self)

    async def on_ready(self):
        self.logger.info("GormBot is ready!")

        if not self.user:
            return

        self.logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
