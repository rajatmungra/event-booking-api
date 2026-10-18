import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BookingNotFound,
    CancellationWindowClosed,
    InvalidBookingStatus,
    InvalidEventStatus,
    SeatNotFound,
    SeatUnavailable,
)
from app.models.booking import Booking, BookingStatus
from app.models.event import Event, EventStatus
from app.models.payment import Payment, PaymentStatus
from app.models.seat import Seat, SeatStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.events import get_event, get_owned_event

HOLD_DURATION = timedelta(minutes=10)
CANCELLATION_DEADLINE = timedelta(hours=24)


def is_free(seat: Seat, now: datetime) -> bool:
    # Expired holds count as free, so no background job is needed for correctness.
    return seat.status == SeatStatus.available or (
        seat.status == SeatStatus.held and seat.held_until < now
    )


async def create_booking(session: AsyncSession, user: User, data: BookingCreate) -> Booking:
    # Shared lock on the event: an organizer cancelling it at this moment waits for us
    # (or we wait for them and then see "cancelled"), so no booking slips past a cancellation.
    event = await get_event(session, data.event_id, user, for_share=True)
    if event.status != EventStatus.published:
        raise InvalidEventStatus("Only published events can be booked.")

    # The core of the project: lock the requested seat rows until this transaction ends.
    # Every other request for any of these seats waits here, then sees our result.
    # ORDER BY id makes every request lock rows in the same order, which prevents deadlocks
    # (A waits for B's seat while B waits for A's).
    seat_ids = sorted(data.seat_ids)
    seats = list(
        await session.scalars(
            select(Seat)
            .where(Seat.event_id == event.id, Seat.id.in_(seat_ids))
            .order_by(Seat.id)
            .with_for_update()
        )
    )

    found = {seat.id for seat in seats}
    missing = [str(seat_id) for seat_id in seat_ids if seat_id not in found]
    if missing:
        await session.rollback()  # release the locks right away instead of at session close
        raise SeatNotFound(details={"seat_ids": missing})

    now = datetime.now(UTC)
    unavailable = [str(seat.id) for seat in seats if not is_free(seat, now)]
    if unavailable:
        await session.rollback()
        raise SeatUnavailable(details={"seat_ids": unavailable})

    held_until = now + HOLD_DURATION
    for seat in seats:
        seat.status = SeatStatus.held
        seat.held_until = held_until
    booking = Booking(
        user_id=user.id,
        event_id=event.id,
        total_cents=sum(seat.price_cents for seat in seats),
        expires_at=held_until,
        seats=sorted(seats, key=lambda seat: (seat.section, seat.row, seat.number)),
    )
    session.add(booking)
    await session.commit()
    return booking


async def list_bookings(session: AsyncSession, user: User) -> list[Booking]:
    bookings = await session.scalars(
        select(Booking)
        .where(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc(), Booking.id)
    )
    return list(bookings)


async def get_booking(
    session: AsyncSession, booking_id: uuid.UUID, user: User, *, for_update: bool = False
) -> Booking:
    booking = await session.get(Booking, booking_id, with_for_update=for_update)
    # Other people's bookings look like they don't exist.
    if booking is None or (user.role != UserRole.admin and booking.user_id != user.id):
        raise BookingNotFound()
    return booking


async def cancel_booking(session: AsyncSession, booking_id: uuid.UUID, user: User) -> Booking:
    # Same lock order as paying: booking, then its seats.
    booking = await get_booking(session, booking_id, user, for_update=True)
    await session.execute(
        select(Seat)
        .where(Seat.id.in_([seat.id for seat in booking.seats]))
        .order_by(Seat.id)
        .with_for_update()
    )

    now = datetime.now(UTC)
    if booking.status not in (BookingStatus.pending, BookingStatus.confirmed):
        raise InvalidBookingStatus(f"Booking is already {booking.status}.")
    if booking.status == BookingStatus.pending and booking.expires_at < now:
        # Its seats may already belong to someone else, so we must not release them.
        raise InvalidBookingStatus("Booking has expired.")
    event = await session.get(Event, booking.event_id)
    if event.starts_at - now < CANCELLATION_DEADLINE:
        raise CancellationWindowClosed()

    for seat in booking.seats:
        seat.status = SeatStatus.available
        seat.held_until = None
    booking.status = BookingStatus.cancelled
    await session.execute(
        update(Payment)
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.succeeded)
        .values(status=PaymentStatus.refunded)
    )
    await session.commit()
    return booking


async def list_event_bookings(
    session: AsyncSession, event_id: uuid.UUID, user: User
) -> list[Booking]:
    await get_owned_event(session, event_id, user)
    bookings = await session.scalars(
        select(Booking)
        .where(Booking.event_id == event_id)
        .order_by(Booking.created_at.desc(), Booking.id)
    )
    return list(bookings)
