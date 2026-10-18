import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SeatStatus(StrEnum):
    available = "available"
    held = "held"
    booked = "booked"


class Seat(Base):
    __tablename__ = "seats"
    # The unique constraint starts with event_id, so its index also speeds up
    # "all seats of this event" queries; no separate index needed.
    __table_args__ = (UniqueConstraint("event_id", "section", "row", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    section: Mapped[str] = mapped_column(String(10))
    row: Mapped[int]
    number: Mapped[int]
    price_cents: Mapped[int]
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus, name="seat_status", native_enum=False, create_constraint=True),
        default=SeatStatus.available,
    )
    held_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
