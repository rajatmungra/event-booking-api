import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from app.api.deps import OptionalUser, OrganizerUser, SessionDep
from app.schemas.booking import BookingRead
from app.schemas.event import EventCreate, EventList, EventRead, EventStats, EventUpdate
from app.services import bookings as booking_service
from app.services import events as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(data: EventCreate, user: OrganizerUser, session: SessionDep) -> EventRead:
    event = await event_service.create_event(session, user, data)
    return EventRead.model_validate(event)


@router.get("")
async def list_events(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    starts_after: AwareDatetime | None = None,
    starts_before: AwareDatetime | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> EventList:
    events, total = await event_service.list_published_events(
        session,
        limit=limit,
        offset=offset,
        starts_after=starts_after,
        starts_before=starts_before,
        q=q,
    )
    return EventList(
        items=[EventRead.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}")
async def get_event(event_id: uuid.UUID, user: OptionalUser, session: SessionDep) -> EventRead:
    event = await event_service.get_event(session, event_id, user)
    return EventRead.model_validate(event)


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID, data: EventUpdate, user: OrganizerUser, session: SessionDep
) -> EventRead:
    event = await event_service.update_event(session, event_id, user, data)
    return EventRead.model_validate(event)


@router.post("/{event_id}/publish")
async def publish_event(event_id: uuid.UUID, user: OrganizerUser, session: SessionDep) -> EventRead:
    event = await event_service.publish_event(session, event_id, user)
    return EventRead.model_validate(event)


@router.post("/{event_id}/cancel")
async def cancel_event(event_id: uuid.UUID, user: OrganizerUser, session: SessionDep) -> EventRead:
    event = await event_service.cancel_event(session, event_id, user)
    return EventRead.model_validate(event)


@router.get("/{event_id}/bookings")
async def list_event_bookings(
    event_id: uuid.UUID, user: OrganizerUser, session: SessionDep
) -> list[BookingRead]:
    bookings = await booking_service.list_event_bookings(session, event_id, user)
    return [BookingRead.model_validate(booking) for booking in bookings]


@router.get("/{event_id}/stats")
async def get_event_stats(
    event_id: uuid.UUID, user: OrganizerUser, session: SessionDep
) -> EventStats:
    return await event_service.get_event_stats(session, event_id, user)
