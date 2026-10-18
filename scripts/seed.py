"""Create demo users, events, seats and bookings.

Run: docker compose exec api uv run python -m scripts.seed
Safe to run again: it does nothing if the demo admin already exists.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import password_hash
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.schemas.event import EventCreate
from app.schemas.seat import SeatLayoutCreate, SectionLayout
from app.schemas.user import UserCreate
from app.services import auth, bookings, events, payments, seats

ADMIN_EMAIL = "admin@example.com"
ORGANIZER_EMAIL = "organizer@example.com"
CUSTOMER_EMAIL = "customer@example.com"

EVENTS = [
    # title, venue, days from now, sections (name, rows, seats per row, price in cents)
    (
        "Jazz Night",
        "Blue Note Hall",
        14,
        [("A", 10, 20, 7500), ("B", 10, 20, 5000), ("C", 10, 20, 2500)],
    ),
    ("Indie Rock Live", "Warehouse 9", 30, [("Floor", 5, 20, 4000), ("Balcony", 3, 15, 6000)]),
    ("Comedy Evening", "Little Theatre", 45, [("Stalls", 8, 12, 3000)]),
]


async def seed(session: AsyncSession, password: str) -> bool:
    if await session.scalar(select(User).where(User.email == ADMIN_EMAIL)):
        return False

    # Admins can't register through the API, so insert the admin directly.
    session.add(
        User(
            email=ADMIN_EMAIL,
            hashed_password=password_hash.hash(password),
            full_name="Demo Admin",
            role=UserRole.admin,
        )
    )
    await session.commit()
    organizer = await auth.register_user(
        session,
        UserCreate(
            email=ORGANIZER_EMAIL, password=password, full_name="Demo Organizer", role="organizer"
        ),
    )
    customer = await auth.register_user(
        session, UserCreate(email=CUSTOMER_EMAIL, password=password, full_name="Demo Customer")
    )

    for title, venue, days, sections in EVENTS:
        starts_at = datetime.now(UTC).replace(
            hour=19, minute=0, second=0, microsecond=0
        ) + timedelta(days=days)
        event = await events.create_event(
            session,
            organizer,
            EventCreate(
                title=title,
                description=f"Demo event: {title}.",
                venue=venue,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=3),
            ),
        )
        layout = SeatLayoutCreate(
            sections=[
                SectionLayout(name=name, rows=rows, seats_per_row=per_row, price_cents=price)
                for name, rows, per_row, price in sections
            ]
        )
        event_seats = await seats.create_layout(session, event.id, organizer, layout)
        await events.publish_event(session, event.id, organizer)

        # One paid booking and one pending hold per event, so the stats aren't empty.
        paid = await bookings.create_booking(
            session,
            customer,
            BookingCreate(event_id=event.id, seat_ids=[s.id for s in event_seats[:2]]),
        )
        await payments.pay_booking(session, paid.id, customer, idempotency_key=f"seed-{paid.id}")
        await bookings.create_booking(
            session, customer, BookingCreate(event_id=event.id, seat_ids=[event_seats[2].id])
        )
    return True


async def main() -> None:
    if not settings.seed_password:
        raise SystemExit("Set SEED_PASSWORD (see .env.example) to run the seed script.")
    async with SessionLocal() as session:
        created = await seed(session, settings.seed_password)
    if created:
        print(f"Seeded demo data. Log in as {ORGANIZER_EMAIL} / {CUSTOMER_EMAIL} / {ADMIN_EMAIL}.")
    else:
        print("Demo data already exists; nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
