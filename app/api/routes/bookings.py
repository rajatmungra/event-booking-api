import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, CustomerUser, SessionDep
from app.schemas.booking import BookingCreate, BookingRead
from app.services import bookings as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_booking(
    data: BookingCreate, user: CustomerUser, session: SessionDep
) -> BookingRead:
    booking = await booking_service.create_booking(session, user, data)
    return BookingRead.model_validate(booking)


@router.get("")
async def list_bookings(user: CurrentUser, session: SessionDep) -> list[BookingRead]:
    bookings = await booking_service.list_bookings(session, user)
    return [BookingRead.model_validate(booking) for booking in bookings]


@router.get("/{booking_id}")
async def get_booking(booking_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> BookingRead:
    booking = await booking_service.get_booking(session, booking_id, user)
    return BookingRead.model_validate(booking)
