from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .DatabaseSchema import Commission


class CommissionConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_commission(self, comm: Commission) -> str | None:
        existing = await self.session.get(Commission, comm.id)
        if existing is not None:
            return "commission already exists!"

        self.session.add(comm)
        await self.session.commit()
        return None

    async def upsert_comm(self, comm: Commission) -> None:
        await self.session.merge(comm)
        await self.session.commit()

    async def delete_comm(self, channel_id: int) -> Optional[Commission]:
        comm = await self.session.get(Commission, channel_id)
        if comm is None:
            return None

        await self.session.delete(comm)
        await self.session.commit()
        return comm

    async def get_comm(self, channel_id: int) -> Optional[Commission]:
        return await self.session.get(Commission, channel_id)
