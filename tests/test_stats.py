from tests.test_bookings import book, event_with_seats
from tests.test_events import create_event
from tests.test_payments import expire_hold, pay


async def test_stats_count_seats_and_revenue(client, organizer_headers, customer_headers):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=8)  # 2500 each
    sold = (await book(client, customer_headers, event, seats[:2])).json()
    await pay(client, customer_headers, sold, key="sold")
    refunded = (await book(client, customer_headers, event, seats[2:3])).json()
    await pay(client, customer_headers, refunded, key="refunded")
    await client.post(f"/bookings/{refunded['id']}/cancel", headers=customer_headers)
    await book(client, customer_headers, event, seats[3:4])  # active hold
    expired = (await book(client, customer_headers, event, seats[4:5])).json()
    await expire_hold(expired)  # expired hold counts as available

    response = await client.get(f"/events/{event['id']}/stats", headers=organizer_headers)

    assert response.status_code == 200
    assert response.json() == {
        "event_id": event["id"],
        "total_seats": 8,
        "seats_sold": 2,
        "seats_held": 1,
        "seats_available": 5,
        "revenue_cents": 5000,  # the refunded payment doesn't count
        "occupancy_percent": 25.0,
    }


async def test_stats_for_event_without_seats(client, organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.get(f"/events/{event['id']}/stats", headers=organizer_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_seats"] == body["revenue_cents"] == 0
    assert body["occupancy_percent"] == 0.0


async def test_stats_are_private_to_the_organizer(
    client, organizer_headers, other_organizer_headers, customer_headers
):
    event = await create_event(client, organizer_headers)
    url = f"/events/{event['id']}/stats"

    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=customer_headers)).status_code == 403
    assert (await client.get(url, headers=other_organizer_headers)).status_code == 403
