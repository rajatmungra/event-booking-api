import uuid
from datetime import UTC, datetime

from sqlalchemy import Row, and_, case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidEventStatus, SeatsAlreadyExist
from app.models.event import EventStatus
from app.models.seat import Seat, SeatStatus
from app.models.user import User
from app.schemas.seat import SeatLayoutCreate
from app.services.events import get_event, get_owned_event


async def list_seats(session: AsyncSession, event_id: uuid.UUID) -> list[Seat]:
    seats = await session.scalars(
        select(Seat).where(Seat.event_id == event_id).order_by(Seat.section, Seat.row, Seat.number)
    )
    return list(seats)


async def create_layout(
    session: AsyncSession, event_id: uuid.UUID, user: User, data: SeatLayoutCreate
) -> list[Seat]:
    # Lock the event row so two layout requests for the same event run one after the
    # other; the second then sees the first one's seats and gets a 409.
    event = await get_owned_event(session, event_id, user, for_update=True)
    if event.status == EventStatus.cancelled:
        raise InvalidEventStatus("Cancelled events can't get a seat layout.")
    if await session.scalar(select(exists().where(Seat.event_id == event_id))):
        raise SeatsAlreadyExist()

    session.add_all(
        Seat(
            event_id=event_id,
            section=section.name,
            row=row,
            number=number,
            price_cents=section.price_cents,
        )
        for section in data.sections
        for row in range(1, section.rows + 1)
        for number in range(1, section.seats_per_row + 1)
    )
    await session.commit()
    return await list_seats(session, event_id)


async def get_seat_map(
    session: AsyncSession, event_id: uuid.UUID, viewer: User | None
) -> list[Row]:
    # Same visibility as the event itself: a draft's seats are hidden from non-owners.
    await get_event(session, event_id, viewer)
    # Expired holds are free to book (see bookings.is_free), so show them as available.
    # CASE computes this in the query; the stored rows are not changed.
    expired_hold = and_(Seat.status == SeatStatus.held, Seat.held_until < datetime.now(UTC))
    status = case((expired_hold, SeatStatus.available.value), else_=Seat.status).label("status")
    rows = await session.execute(
        select(Seat.id, Seat.section, Seat.row, Seat.number, Seat.price_cents, status)
        .where(Seat.event_id == event_id)
        .order_by(Seat.section, Seat.row, Seat.number)
    )
    return list(rows)
