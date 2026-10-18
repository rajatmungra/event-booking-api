import uuid

from fastapi import APIRouter, status

from app.api.deps import OptionalUser, OrganizerUser, SessionDep
from app.schemas.seat import SeatLayoutCreate, SeatRead
from app.services import seats as seat_service

router = APIRouter(prefix="/events/{event_id}/seats", tags=["seats"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_layout(
    event_id: uuid.UUID, data: SeatLayoutCreate, user: OrganizerUser, session: SessionDep
) -> list[SeatRead]:
    seats = await seat_service.create_layout(session, event_id, user, data)
    return [SeatRead.model_validate(seat) for seat in seats]


@router.get("")
async def get_seat_map(
    event_id: uuid.UUID, user: OptionalUser, session: SessionDep
) -> list[SeatRead]:
    seats = await seat_service.get_seat_map(session, event_id, user)
    return [SeatRead.model_validate(seat) for seat in seats]
