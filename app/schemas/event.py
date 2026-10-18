import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.event import EventStatus


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    venue: str = Field(min_length=1, max_length=200)
    # AwareDatetime rejects timestamps without a timezone, e.g. "2026-12-01T19:00:00".
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class EventUpdate(BaseModel):
    # PATCH: every field is optional; fields left out (or sent as null) stay unchanged.
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    venue: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organizer_id: uuid.UUID
    title: str
    description: str
    venue: str
    starts_at: datetime
    ends_at: datetime
    status: EventStatus
    created_at: datetime
    updated_at: datetime


class EventList(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int


class EventStats(BaseModel):
    event_id: uuid.UUID
    total_seats: int
    seats_sold: int
    seats_held: int
    seats_available: int
    revenue_cents: int
    occupancy_percent: float
