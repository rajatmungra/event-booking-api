import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models.seat import Seat
from tests.conftest import TestSession
from tests.test_events import create_event, create_published_event


async def event_with_seats(client, headers, seats_per_row=5, publish=True) -> tuple[dict, list]:
    create = create_published_event if publish else create_event
    event = await create(client, headers)
    layout = {
        "sections": [{"name": "A", "rows": 1, "seats_per_row": seats_per_row, "price_cents": 2500}]
    }
    response = await client.post(f"/events/{event['id']}/seats", json=layout, headers=headers)
    assert response.status_code == 201, response.text
    return event, response.json()


async def book(client, headers, event, seats):
    return await client.post(
        "/bookings",
        json={"event_id": event["id"], "seat_ids": [seat["id"] for seat in seats]},
        headers=headers,
    )


# --- POST /bookings ---


async def test_customer_holds_seats(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)

    response = await book(client, customer_headers, event, seats[:2])

    assert response.status_code == 201
    booking = response.json()
    assert booking["status"] == "pending"
    assert booking["total_cents"] == 5000
    assert [seat["id"] for seat in booking["seats"]] == [seat["id"] for seat in seats[:2]]
    hold = datetime.fromisoformat(booking["expires_at"]) - datetime.now(UTC)
    assert timedelta(minutes=9) < hold <= timedelta(minutes=10)

    seat_map = (await client.get(f"/events/{event['id']}/seats")).json()
    assert [seat["status"] for seat in seat_map] == [
        "held",
        "held",
        "available",
        "available",
        "available",
    ]


async def test_booking_requires_login(client, organizer_headers):
    event, seats = await event_with_seats(client, organizer_headers)

    response = await book(client, {}, event, seats[:1])

    assert response.status_code == 401


async def test_organizer_cannot_book(client, organizer_headers):
    event, seats = await event_with_seats(client, organizer_headers)

    response = await book(client, organizer_headers, event, seats[:1])

    assert response.status_code == 403


async def test_held_seat_cannot_be_booked_again(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    await book(client, customer_headers, event, seats[:2])

    response = await book(client, customer_headers, event, seats[1:3])

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SEAT_UNAVAILABLE"
    assert error["details"] == {"seat_ids": [seats[1]["id"]]}
    # The failed request must not have held the free seat either.
    seat_map = (await client.get(f"/events/{event['id']}/seats")).json()
    assert seat_map[2]["status"] == "available"


async def test_expired_hold_counts_as_free(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    await book(client, customer_headers, event, seats[:1])
    async with TestSession() as session:
        await session.execute(
            update(Seat)
            .where(Seat.id == uuid.UUID(seats[0]["id"]))
            .values(held_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    response = await book(client, customer_headers, event, seats[:1])

    assert response.status_code == 201


async def test_seat_from_another_event_is_rejected(client, organizer_headers, customer_headers):
    event, _ = await event_with_seats(client, organizer_headers)
    _, other_seats = await event_with_seats(client, organizer_headers)

    response = await book(client, customer_headers, event, other_seats[:1])

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "SEAT_NOT_FOUND"
    assert error["details"] == {"seat_ids": [other_seats[0]["id"]]}


async def test_invalid_seat_lists_are_rejected(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=11)

    for seat_list in ([], [seats[0], seats[0]], seats):  # empty, duplicate, 11 seats
        response = await book(client, customer_headers, event, seat_list)
        assert response.status_code == 422, seat_list


async def test_draft_event_cannot_be_booked(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers, publish=False)

    response = await book(client, customer_headers, event, seats[:1])

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVENT_NOT_FOUND"


async def test_cancelled_event_cannot_be_booked(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    response = await book(client, customer_headers, event, seats[:1])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_EVENT_STATUS"


# --- GET /bookings and /bookings/{id} ---


async def test_list_shows_only_my_bookings(
    client, organizer_headers, customer_headers, admin_headers
):
    event, seats = await event_with_seats(client, organizer_headers)
    first = (await book(client, customer_headers, event, seats[:1])).json()
    second = (await book(client, customer_headers, event, seats[1:2])).json()
    await book(client, admin_headers, event, seats[2:3])

    response = await client.get("/bookings", headers=customer_headers)

    assert response.status_code == 200
    assert [booking["id"] for booking in response.json()] == [second["id"], first["id"]]


async def test_list_bookings_requires_login(client):
    response = await client.get("/bookings")

    assert response.status_code == 401


async def test_owner_and_admin_can_view_booking(
    client, organizer_headers, customer_headers, admin_headers
):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:2])).json()

    for headers in (customer_headers, admin_headers):
        response = await client.get(f"/bookings/{booking['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json() == booking


async def test_other_users_booking_is_hidden(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers)
    booking = (await book(client, customer_headers, event, seats[:1])).json()

    response = await client.get(f"/bookings/{booking['id']}", headers=organizer_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BOOKING_NOT_FOUND"
