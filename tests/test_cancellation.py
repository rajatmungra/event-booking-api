import uuid

from sqlalchemy import select

from app.models.payment import Payment
from tests.conftest import TestSession
from tests.test_bookings import book, event_with_seats
from tests.test_events import in_days
from tests.test_payments import expire_hold, pay


async def payment_statuses(booking: dict) -> list[str]:
    async with TestSession() as session:
        payments = await session.scalars(
            select(Payment.status).where(Payment.booking_id == uuid.UUID(booking["id"]))
        )
        return list(payments)


async def cancel(client, headers, booking):
    return await client.post(f"/bookings/{booking['id']}/cancel", headers=headers)


# --- POST /bookings/{id}/cancel ---


async def test_customer_cancels_pending_booking(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:2])).json()

    response = await cancel(client, customer_headers, booking)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert [seat["status"] for seat in body["seats"]] == ["available", "available"]
    # The seats can be booked again right away.
    assert (await book(client, customer_headers, event, seats[:2])).status_code == 201


async def test_cancelling_paid_booking_refunds_payment(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()
    await pay(client, customer_headers, booking)

    response = await cancel(client, customer_headers, booking)

    assert response.status_code == 200
    assert response.json()["seats"][0]["status"] == "available"
    assert await payment_statuses(booking) == ["refunded"]


async def test_cancel_closes_24_hours_before_event(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(
        client, organizer_headers, starts_at=in_days(0.5), ends_at=in_days(0.6)
    )
    booking = (await book(client, customer_headers, event, seats[:1])).json()
    await pay(client, customer_headers, booking)

    response = await cancel(client, customer_headers, booking)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANCELLATION_WINDOW_CLOSED"
    assert await payment_statuses(booking) == ["succeeded"]


async def test_cancel_twice_is_rejected(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()
    await cancel(client, customer_headers, booking)

    response = await cancel(client, customer_headers, booking)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_BOOKING_STATUS"


async def test_expired_booking_cannot_be_cancelled(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()
    await expire_hold(booking)
    # Someone else takes the freed seat; cancelling the old booking must not release it.
    newer = (await book(client, customer_headers, event, seats[:1])).json()

    response = await cancel(client, customer_headers, booking)

    assert response.status_code == 409
    after = (await client.get(f"/bookings/{newer['id']}", headers=customer_headers)).json()
    assert after["seats"][0]["status"] == "held"


async def test_cancel_requires_login(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()

    assert (await cancel(client, {}, booking)).status_code == 401


async def test_other_user_cannot_cancel_booking(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()

    response = await cancel(client, organizer_headers, booking)

    assert response.status_code == 404


# --- POST /events/{id}/cancel cascades ---


async def test_cancelling_event_cancels_and_refunds_its_bookings(
    client, organizer_headers, customer_headers
):
    event, seats = await event_with_seats(client, organizer_headers)
    paid = (await book(client, customer_headers, event, seats[:1])).json()
    await pay(client, customer_headers, paid)
    pending = (await book(client, customer_headers, event, seats[1:2])).json()
    other_event, other_seats = await event_with_seats(client, organizer_headers)
    untouched = (await book(client, customer_headers, other_event, other_seats[:1])).json()

    response = await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    assert response.status_code == 200
    for booking in (paid, pending):
        after = (await client.get(f"/bookings/{booking['id']}", headers=customer_headers)).json()
        assert after["status"] == "cancelled"
    assert await payment_statuses(paid) == ["refunded"]
    seat_map = (await client.get(f"/events/{event['id']}/seats")).json()
    assert {seat["status"] for seat in seat_map} == {"available"}
    other = (await client.get(f"/bookings/{untouched['id']}", headers=customer_headers)).json()
    assert other["status"] == "pending"


# --- GET /events/{id}/bookings ---


async def test_organizer_lists_event_bookings(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    first = (await book(client, customer_headers, event, seats[:1])).json()
    second = (await book(client, customer_headers, event, seats[1:2])).json()
    me = (await client.get("/users/me", headers=customer_headers)).json()

    response = await client.get(f"/events/{event['id']}/bookings", headers=organizer_headers)

    assert response.status_code == 200
    bookings = response.json()
    assert [booking["id"] for booking in bookings] == [second["id"], first["id"]]
    assert {booking["user_id"] for booking in bookings} == {me["id"]}


async def test_event_bookings_are_private_to_the_organizer(
    client, organizer_headers, other_organizer_headers, customer_headers
):
    event, _ = await event_with_seats(client, organizer_headers)
    url = f"/events/{event['id']}/bookings"

    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=customer_headers)).status_code == 403
    assert (await client.get(url, headers=other_organizer_headers)).status_code == 403
