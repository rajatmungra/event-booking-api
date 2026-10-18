import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EventNotFound,
    InvalidEventStatus,
    InvalidEventTimes,
    PermissionDenied,
)
from app.models.event import Event, EventStatus
from app.models.user import User, UserRole
from app.schemas.event import EventCreate, EventUpdate


def can_manage(event: Event, user: User | None) -> bool:
    return user is not None and (user.role == UserRole.admin or event.organizer_id == user.id)


def check_event_times(starts_at: datetime, ends_at: datetime, *, check_future: bool) -> None:
    if ends_at <= starts_at:
        raise InvalidEventTimes("ends_at must be after starts_at.")
    if check_future and starts_at <= datetime.now(UTC):
        raise InvalidEventTimes("starts_at must be in the future.")


async def get_owned_event(session: AsyncSession, event_id: uuid.UUID, user: User) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise EventNotFound()
    if not can_manage(event, user):
        raise PermissionDenied("Only the event's organizer can do this.")
    return event


async def create_event(session: AsyncSession, organizer: User, data: EventCreate) -> Event:
    check_event_times(data.starts_at, data.ends_at, check_future=True)
    event = Event(organizer_id=organizer.id, **data.model_dump())
    session.add(event)
    await session.commit()
    return event


async def list_published_events(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    starts_after: datetime | None,
    starts_before: datetime | None,
    q: str | None,
) -> tuple[list[Event], int]:
    query = select(Event).where(Event.status == EventStatus.published)
    if starts_after is not None:
        query = query.where(Event.starts_at >= starts_after)
    if starts_before is not None:
        query = query.where(Event.starts_at <= starts_before)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Event.title.ilike(pattern),
                Event.description.ilike(pattern),
                Event.venue.ilike(pattern),
            )
        )

    # Count all matches (ignoring limit/offset) so clients know how many pages exist.
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    # Event.id breaks ties so pages stay stable when two events start at the same time.
    events = await session.scalars(
        query.order_by(Event.starts_at, Event.id).limit(limit).offset(offset)
    )
    return list(events), total


async def get_event(session: AsyncSession, event_id: uuid.UUID, viewer: User | None) -> Event:
    event = await session.get(Event, event_id)
    # Drafts are private: to everyone except the owner they look like they don't exist.
    if event is None or (event.status == EventStatus.draft and not can_manage(event, viewer)):
        raise EventNotFound()
    return event


async def update_event(
    session: AsyncSession, event_id: uuid.UUID, user: User, data: EventUpdate
) -> Event:
    event = await get_owned_event(session, event_id, user)
    if event.status == EventStatus.cancelled:
        raise InvalidEventStatus("Cancelled events can't be edited.")

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    check_event_times(
        changes.get("starts_at", event.starts_at),
        changes.get("ends_at", event.ends_at),
        check_future="starts_at" in changes,
    )
    for field, value in changes.items():
        setattr(event, field, value)
    await session.commit()
    return event


async def publish_event(session: AsyncSession, event_id: uuid.UUID, user: User) -> Event:
    event = await get_owned_event(session, event_id, user)
    if event.status != EventStatus.draft:
        raise InvalidEventStatus("Only draft events can be published.")
    event.status = EventStatus.published
    await session.commit()
    return event


async def cancel_event(session: AsyncSession, event_id: uuid.UUID, user: User) -> Event:
    event = await get_owned_event(session, event_id, user)
    if event.status == EventStatus.cancelled:
        raise InvalidEventStatus("Event is already cancelled.")
    event.status = EventStatus.cancelled
    await session.commit()
    return event
