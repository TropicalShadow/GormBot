from typing import List, Literal, Optional

from dataclasses import dataclass
from dataclasses_json import dataclass_json

from . import DatabaseConnection


TICKET_CATEGORY = Literal[
    "builder",
    "developer",
    "support",
    "misc",
]


@dataclass_json
@dataclass
class IndividualTicket:
    channel_id: int
    author_id: int
    author_name: str
    category: TICKET_CATEGORY
    first_message: Optional[int] = None


class TicketConnection(DatabaseConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def channel_exists(self, channel_id: int | str) -> bool:
        with self as db:
            return str(channel_id) in db

    def create_ticket(
        self,
        ticket_details: IndividualTicket,
    ) -> str | None:
        channel_id = str(ticket_details.channel_id)

        with self as db:
            if channel_id in db:
                return "Ticket already exists!"

            db[channel_id] = ticket_details.to_dict()

        return None

    def upsert_ticket(
        self,
        ticket_details: IndividualTicket,
    ) -> None:
        with self as db:
            db[str(ticket_details.channel_id)] = ticket_details.to_dict()

    def delete_ticket(
        self,
        channel_id: str | int,
    ) -> Optional[IndividualTicket]:
        with self as db:
            data = db.pop(str(channel_id), None)

            if data is None:
                return None

            return IndividualTicket.from_dict(data)

    def get_ticket(
        self,
        channel_id: str | int,
    ) -> Optional[IndividualTicket]:
        with self as db:
            data = db.get(str(channel_id))

            if data is None:
                return None

            return IndividualTicket.from_dict(data)

    def get_all_ticket_ids(self) -> List[str]:
        with self as db:
            return list(db.keys())
