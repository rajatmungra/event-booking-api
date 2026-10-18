import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.seat import Seat


class BookingStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"


# A plain association table (no model class): it only links bookings to seats.
booking_seats = Table(
    "booking_seats",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id"), primary_key=True),
    Column("seat_id", ForeignKey("seats.id"), primary_key=True),
)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, create_constraint=True),
        default=BookingStatus.pending,
    )
    total_cents: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Many-to-many through booking_seats. lazy="selectin" loads the seats right away with a
    # second SELECT whenever bookings are loaded, so async code never needs a lazy load.
    seats: Mapped[list[Seat]] = relationship(
        secondary=booking_seats, lazy="selectin", order_by=(Seat.section, Seat.row, Seat.number)
    )
