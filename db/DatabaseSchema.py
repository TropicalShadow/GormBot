from typing import Optional
from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import enum


class Base(DeclarativeBase):
    pass


class TicketCategory(str, enum.Enum):
    builder = "builder"
    developer = "developer"
    support = "support"
    misc = "misc"
    application = "application"


class CommissionStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class IndividualTicket(Base):
    __tablename__ = "tickets"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_name: Mapped[str] = mapped_column(String, nullable=False)

    category: Mapped[TicketCategory] = mapped_column(
        Enum(TicketCategory, native_enum=False),
        nullable=False
    )

    first_message: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    voice_channel: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    commission: Mapped["Commission"] = relationship(
        back_populates="ticket",
        uselist=False,
    )


class Commission(Base):
    __tablename__ = "commission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    project_name: Mapped[str] = mapped_column(String, nullable=False)
    budget: Mapped[str] = mapped_column(String, nullable=False)
    brief: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)

    ticket_channel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tickets.channel_id"),
        nullable=True,
        unique=True,
    )

    ticket: Mapped[IndividualTicket] = relationship(
        IndividualTicket,
        back_populates="commission",
    )

    status: Mapped[CommissionStatus] = mapped_column(
        Enum(CommissionStatus, native_enum=False),
        nullable=False,
    )
