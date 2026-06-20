from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .DatabaseSchema import BotConfig


class ConfigConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        result = await self.session.get(BotConfig, key)
        return result.value if result else None

    async def set(self, key: str, value: str) -> None:
        existing = await self.session.get(BotConfig, key)
        if existing:
            existing.value = value
        else:
            self.session.add(BotConfig(key=key, value=value))
        await self.session.commit()

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(select(BotConfig))
        return {row.key: row.value for row in result.scalars().all()}
