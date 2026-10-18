import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.booking import BookingStatus
from app.schemas.seat import SeatRead


class BookingCreate(BaseModel):
    event_id: uuid.UUID
    seat_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)

    @field_validator("seat_ids")
    @classmethod
    def check_unique(cls, seat_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(seat_ids) != len(set(seat_ids)):
            raise ValueError("Seat ids must be unique.")
        return seat_ids


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    status: BookingStatus
    total_cents: int
    expires_at: datetime
    created_at: datetime
    seats: list[SeatRead]
