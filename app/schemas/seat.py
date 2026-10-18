import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.seat import SeatStatus

MAX_SEATS_PER_LAYOUT = 10_000


class SectionLayout(BaseModel):
    name: str = Field(min_length=1, max_length=10)
    rows: int = Field(ge=1, le=100)
    seats_per_row: int = Field(ge=1, le=100)
    price_cents: int = Field(ge=0)


class SeatLayoutCreate(BaseModel):
    sections: list[SectionLayout] = Field(min_length=1, max_length=26)

    # model_validator(mode="after") runs once all fields are validated, so it can check
    # rules that involve several fields or list items together.
    @model_validator(mode="after")
    def check_layout(self) -> "SeatLayoutCreate":
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("Section names must be unique.")
        total = sum(section.rows * section.seats_per_row for section in self.sections)
        if total > MAX_SEATS_PER_LAYOUT:
            raise ValueError(f"A layout can have at most {MAX_SEATS_PER_LAYOUT} seats.")
        return self


class SeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: str
    row: int
    number: int
    price_cents: int
    status: SeatStatus
