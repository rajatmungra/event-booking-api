"""The project's core guarantee: a seat can never be double-booked.

Each request below gets its own DB session and connection, so Postgres sees real concurrent
transactions racing for the same rows.
"""

import asyncio
import random

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.booking import Booking, BookingStatus
from app.models.user import User, UserRole
from tests.conftest import TestSession
from tests.test_bookings import book, event_with_seats
from tests.test_payments import count_payments, pay


@pytest.fixture
async def many_customer_headers() -> list[dict[str, str]]:
    # Insert the users directly and mint tokens, instead of 50 slow argon2 logins.
    users = [
        User(
            email=f"racer{i}@example.com",
            hashed_password="unused",
            full_name=f"Racer {i}",
            role=UserRole.customer,
        )
        for i in range(50)
    ]
    async with TestSession() as session:
        session.add_all(users)
        await session.commit()
    return [{"Authorization": f"Bearer {create_access_token(user.id)}"} for user in users]


async def count_bookings() -> int:
    async with TestSession() as session:
        return await session.scalar(select(func.count()).select_from(Booking))


async def test_50_customers_race_for_one_seat(client, organizer_headers, many_customer_headers):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=1)

    responses = await asyncio.gather(
        *(book(client, headers, event, seats) for headers in many_customer_headers)
    )

    statuses = [response.status_code for response in responses]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 49
    assert await count_bookings() == 1
    seat_map = (await client.get(f"/events/{event['id']}/seats")).json()
    assert seat_map[0]["status"] == "held"


async def test_overlapping_requests_in_any_order_never_deadlock(
    client, organizer_headers, many_customer_headers
):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=3)

    def shuffled():
        return random.sample(seats, k=len(seats))

    # A deadlock would make Postgres abort a transaction, which surfaces as an exception here.
    # Note: for this simple query Postgres tends to lock rows in the same order even without
    # ORDER BY; ORDER BY in the service makes that order guaranteed for any query plan.
    responses = await asyncio.gather(
        *(book(client, headers, event, shuffled()) for headers in many_customer_headers[:20])
    )

    statuses = [response.status_code for response in responses]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 19
    assert await count_bookings() == 1


async def test_parallel_retries_with_same_key_pay_once(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()

    # A client retrying a slow request: 10 identical pay calls at the same moment.
    responses = await asyncio.gather(
        *(pay(client, customer_headers, booking, key="retry-key") for _ in range(10))
    )

    assert {response.status_code for response in responses} == {200}
    assert len({response.json()["id"] for response in responses}) == 1
    assert await count_payments() == 1


async def test_event_cancel_racing_bookings_leaves_no_active_booking(
    client, organizer_headers, many_customer_headers
):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=10)

    # 10 customers each book a different seat while the organizer cancels the event.
    responses = await asyncio.gather(
        *(
            book(client, headers, event, [seat])
            for headers, seat in zip(many_customer_headers[:10], seats, strict=True)
        ),
        client.post(f"/events/{event['id']}/cancel", headers=organizer_headers),
    )

    *booking_responses, cancel_response = responses
    assert cancel_response.status_code == 200
    assert {r.status_code for r in booking_responses} <= {201, 409}
    async with TestSession() as session:
        active = await session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]))
        )
    assert active == 0
