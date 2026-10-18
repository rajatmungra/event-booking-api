import asyncio
import uuid

import pytest

from tests.test_events import create_event, create_published_event

# 3 sections x 10 rows x 20 seats = 600 seats.
LAYOUT = {
    "sections": [
        {"name": "A", "rows": 10, "seats_per_row": 20, "price_cents": 7500},
        {"name": "B", "rows": 10, "seats_per_row": 20, "price_cents": 5000},
        {"name": "C", "rows": 10, "seats_per_row": 20, "price_cents": 2500},
    ]
}


def section(name="A", rows=2, seats_per_row=3, price_cents=1000) -> dict:
    return {"name": name, "rows": rows, "seats_per_row": seats_per_row, "price_cents": price_cents}


# --- POST /events/{id}/seats ---


async def test_organizer_creates_600_seat_layout_in_one_request(client, organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json=LAYOUT, headers=organizer_headers
    )

    assert response.status_code == 201
    seats = response.json()
    assert len(seats) == 600
    assert {seat["status"] for seat in seats} == {"available"}
    assert seats[0] | {"id": None} == {
        "id": None,
        "section": "A",
        "row": 1,
        "number": 1,
        "price_cents": 7500,
        "status": "available",
    }
    assert (seats[-1]["section"], seats[-1]["row"], seats[-1]["number"]) == ("C", 10, 20)


async def test_layout_can_be_added_to_published_event(client, organizer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json={"sections": [section()]}, headers=organizer_headers
    )

    assert response.status_code == 201
    assert len(response.json()) == 6


async def test_admin_can_create_layout_for_any_event(client, organizer_headers, admin_headers):
    event = await create_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json={"sections": [section()]}, headers=admin_headers
    )

    assert response.status_code == 201


async def test_create_layout_requires_login(client, organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.post(f"/events/{event['id']}/seats", json=LAYOUT)

    assert response.status_code == 401


async def test_customer_cannot_create_layout(client, organizer_headers, customer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json=LAYOUT, headers=customer_headers
    )

    assert response.status_code == 403


async def test_other_organizer_cannot_create_layout(
    client, organizer_headers, other_organizer_headers
):
    event = await create_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json=LAYOUT, headers=other_organizer_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_second_layout_is_rejected(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    url = f"/events/{event['id']}/seats"
    await client.post(url, json={"sections": [section("A")]}, headers=organizer_headers)

    response = await client.post(url, json={"sections": [section("B")]}, headers=organizer_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEATS_ALREADY_EXIST"


async def test_concurrent_layouts_create_only_one(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    url = f"/events/{event['id']}/seats"

    # Different section names, so only the event-row lock (not the unique constraint)
    # can stop both requests from inserting seats.
    responses = await asyncio.gather(
        client.post(url, json={"sections": [section("A")]}, headers=organizer_headers),
        client.post(url, json={"sections": [section("B")]}, headers=organizer_headers),
    )

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len((await client.get(url, headers=organizer_headers)).json()) == 6


async def test_cancelled_event_cannot_get_layout(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json=LAYOUT, headers=organizer_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_EVENT_STATUS"


async def test_layout_for_unknown_event_returns_404(client, organizer_headers):
    response = await client.post(
        f"/events/{uuid.uuid4()}/seats", json=LAYOUT, headers=organizer_headers
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "sections",
    [
        [section("A"), section("A")],  # duplicate section names
        [section(price_cents=-1)],  # negative price
        [section(rows=0)],  # empty section
        [section("A", 100, 100), section("B", 1, 1)],  # 10,001 seats, over the cap
        [],  # no sections
    ],
)
async def test_invalid_layout_is_rejected(client, organizer_headers, sections):
    event = await create_event(client, organizer_headers)

    response = await client.post(
        f"/events/{event['id']}/seats", json={"sections": sections}, headers=organizer_headers
    )

    assert response.status_code == 422


# --- GET /events/{id}/seats ---


async def test_seat_map_of_published_event_is_public(client, organizer_headers):
    event = await create_published_event(client, organizer_headers)
    await client.post(
        f"/events/{event['id']}/seats",
        json={"sections": [section("B", price_cents=500), section("A", price_cents=900)]},
        headers=organizer_headers,
    )

    response = await client.get(f"/events/{event['id']}/seats")

    assert response.status_code == 200
    seats = response.json()
    assert len(seats) == 12
    # Sorted by section, row, number regardless of the order sections were sent in.
    assert [(s["section"], s["row"], s["number"]) for s in seats[:4]] == [
        ("A", 1, 1),
        ("A", 1, 2),
        ("A", 1, 3),
        ("A", 2, 1),
    ]
    assert {s["price_cents"] for s in seats if s["section"] == "B"} == {500}


async def test_seat_map_of_draft_is_hidden_from_public(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    url = f"/events/{event['id']}/seats"
    await client.post(url, json={"sections": [section()]}, headers=organizer_headers)

    assert (await client.get(url)).status_code == 404
    assert (await client.get(url, headers=organizer_headers)).status_code == 200


async def test_seat_map_of_unknown_event_returns_404(client):
    response = await client.get(f"/events/{uuid.uuid4()}/seats")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVENT_NOT_FOUND"
