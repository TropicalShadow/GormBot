from typing import TYPE_CHECKING
from . import DatabaseConnection, TicketConnection


if TYPE_CHECKING:
    from utils import GormBot


class DatabaseManager:
    TICKET_SYSTEM_DATABASE_FILE = "ticket_system.sqlite3"

    def __init__(self, bot: "GormBot"):
        self.bot = bot

    def load(self) -> tuple[bool, str]:
        try:
            with self.ticket_system_table:
                pass
        except Exception as e:
            return False, str(e)
        return True, "Database loaded successfully"

    @property
    def ticket_system_table(self) -> TicketConnection:
        return TicketConnection(DatabaseManager.TICKET_SYSTEM_DATABASE_FILE, "TicketSystem")
