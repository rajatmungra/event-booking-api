import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BookingExpired, IdempotencyKeyReused, InvalidBookingStatus
from app.models.booking import BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.models.seat import Seat, SeatStatus
from app.models.user import User
from app.services.bookings import get_booking


async def pay_booking(
    session: AsyncSession, booking_id: uuid.UUID, user: User, idempotency_key: str
) -> Payment:
    # Lock the booking first: a retry with the same key waits here until the first request
    # commits, and then finds its payment below instead of paying twice.
    booking = await get_booking(session, booking_id, user, for_update=True)

    previous = await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.booking_id != booking.id:
            raise IdempotencyKeyReused()
        return previous  # replay: same key, same answer, nothing new happens

    # Lock the seats too (same order as create_booking). Otherwise, while we pay, the hold
    # could expire and another customer could take a seat we're about to mark as booked.
    await session.execute(
        select(Seat)
        .where(Seat.id.in_([seat.id for seat in booking.seats]))
        .order_by(Seat.id)
        .with_for_update()
    )

    if booking.status != BookingStatus.pending:
        raise InvalidBookingStatus(f"Booking is {booking.status}, not pending.")
    if booking.expires_at < datetime.now(UTC):
        booking.status = BookingStatus.expired
        await session.commit()  # save the new status before reporting the error
        raise BookingExpired()

    payment = Payment(
        booking_id=booking.id,
        amount_cents=booking.total_cents,
        status=PaymentStatus.succeeded,  # mock payment: always succeeds
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    for seat in booking.seats:
        seat.status = SeatStatus.booked
        seat.held_until = None
    booking.status = BookingStatus.confirmed
    try:
        await session.commit()
    except IntegrityError:
        # The same key was used at the same moment for a different booking.
        await session.rollback()
        raise IdempotencyKeyReused() from None
    return payment
