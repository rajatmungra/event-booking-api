import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.models.booking import Booking
from app.models.payment import Payment
from app.models.seat import Seat
from tests.conftest import TestSession
from tests.test_bookings import book, event_with_seats


async def pay(client, headers, booking, key="key-1"):
    return await client.post(
        f"/bookings/{booking['id']}/pay", headers=headers | {"Idempotency-Key": key}
    )


async def count_payments() -> int:
    async with TestSession() as session:
        return await session.scalar(select(func.count()).select_from(Payment))


async def expire_hold(booking: dict) -> None:
    # Move the hold into the past, as if 10 minutes had gone by.
    past = datetime.now(UTC) - timedelta(seconds=1)
    seat_ids = [uuid.UUID(seat["id"]) for seat in booking["seats"]]
    async with TestSession() as session:
        await session.execute(
            update(Booking).where(Booking.id == uuid.UUID(booking["id"])).values(expires_at=past)
        )
        await session.execute(update(Seat).where(Seat.id.in_(seat_ids)).values(held_until=past))
        await session.commit()


async def held_booking(client, organizer_headers, customer_headers) -> tuple[dict, dict]:
    event, seats = await event_with_seats(client, organizer_headers)
    response = await book(client, customer_headers, event, seats[:2])
    assert response.status_code == 201, response.text
    return event, response.json()


async def test_customer_pays_booking(client, organizer_headers, customer_headers):
    event, booking = await held_booking(client, organizer_headers, customer_headers)

    response = await pay(client, customer_headers, booking)

    assert response.status_code == 200
    payment = response.json()
    assert payment["status"] == "succeeded"
    assert payment["amount_cents"] == booking["total_cents"]
    assert payment["booking_id"] == booking["id"]
    after = (await client.get(f"/bookings/{booking['id']}", headers=customer_headers)).json()
    assert after["status"] == "confirmed"
    assert [seat["status"] for seat in after["seats"]] == ["booked", "booked"]


async def test_same_key_twice_creates_one_payment(client, organizer_headers, customer_headers):
    _, booking = await held_booking(client, organizer_headers, customer_headers)

    first = await pay(client, customer_headers, booking)
    second = await pay(client, customer_headers, booking)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert await count_payments() == 1


async def test_booked_seat_cannot_be_booked_again(client, organizer_headers, customer_headers):
    event, booking = await held_booking(client, organizer_headers, customer_headers)
    await pay(client, customer_headers, booking)
    await expire_hold(booking)  # even long after the hold time, a booked seat stays booked

    response = await book(client, customer_headers, event, booking["seats"][:1])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEAT_UNAVAILABLE"


async def test_pay_requires_login(client, organizer_headers, customer_headers):
    _, booking = await held_booking(client, organizer_headers, customer_headers)

    response = await pay(client, {}, booking)

    assert response.status_code == 401


async def test_other_user_cannot_pay_booking(client, organizer_headers, customer_headers):
    _, booking = await held_booking(client, organizer_headers, customer_headers)

    response = await pay(client, organizer_headers, booking)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BOOKING_NOT_FOUND"


async def test_pay_requires_idempotency_key(client, organizer_headers, customer_headers):
    _, booking = await held_booking(client, organizer_headers, customer_headers)

    response = await client.post(f"/bookings/{booking['id']}/pay", headers=customer_headers)

    assert response.status_code == 422
    assert await count_payments() == 0


async def test_expired_booking_returns_410(client, organizer_headers, customer_headers):
    _, booking = await held_booking(client, organizer_headers, customer_headers)
    await expire_hold(booking)

    response = await pay(client, customer_headers, booking)

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "BOOKING_EXPIRED"
    assert await count_payments() == 0
    after = (await client.get(f"/bookings/{booking['id']}", headers=customer_headers)).json()
    assert after["status"] == "expired"


async def test_confirmed_booking_cannot_be_paid_with_new_key(
    client, organizer_headers, customer_headers
):
    _, booking = await held_booking(client, organizer_headers, customer_headers)
    await pay(client, customer_headers, booking, key="key-1")

    response = await pay(client, customer_headers, booking, key="key-2")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_BOOKING_STATUS"
    assert await count_payments() == 1


async def test_key_cannot_be_reused_for_another_booking(
    client, organizer_headers, customer_headers
):
    event, seats = await event_with_seats(client, organizer_headers)
    first = (await book(client, customer_headers, event, seats[:1])).json()
    second = (await book(client, customer_headers, event, seats[1:2])).json()
    await pay(client, customer_headers, first, key="shared-key")

    response = await pay(client, customer_headers, second, key="shared-key")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert await count_payments() == 1
