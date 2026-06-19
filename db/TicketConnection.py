from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .DatabaseSchema import IndividualTicket


class TicketConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def channel_exists(self, channel_id: int) -> bool:
        result = await self.session.get(IndividualTicket, channel_id)
        return result is not None

    async def create_ticket(self, ticket: IndividualTicket) -> str | None:
        existing = await self.session.get(IndividualTicket, ticket.channel_id)
        if existing is not None:
            return "Ticket already exists!"

        self.session.add(ticket)
        await self.session.commit()
        return None

    async def upsert_ticket(self, ticket: IndividualTicket) -> None:
        await self.session.merge(ticket)
        await self.session.commit()

    async def delete_ticket(self, channel_id: int) -> Optional[IndividualTicket]:
        ticket = await self.session.get(IndividualTicket, channel_id)
        if ticket is None:
            return None

        await self.session.delete(ticket)
        await self.session.commit()
        return ticket

    async def get_ticket(self, channel_id: int) -> Optional[IndividualTicket]:
        return await self.session.get(IndividualTicket, channel_id)

    async def get_all_ticket_ids(self) -> List[int]:
        result = await self.session.execute(
            select(IndividualTicket.channel_id)
        )
        return list(result.scalars().all())

    async def get_active_voice_channels(self) -> List[int]:
        result = await self.session.execute(
            select(IndividualTicket.voice_channel).where(
                IndividualTicket.voice_channel.isnot(None)
            )
        )
        return list(result.scalars().all())

    async def is_active_voice_channel(self, channel_id: int) -> bool:
        result = await self.session.execute(
            select(IndividualTicket).where(
                IndividualTicket.voice_channel == channel_id
            )
        )
        return result.scalar_one_or_none() is not None
