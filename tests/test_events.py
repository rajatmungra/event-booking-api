import uuid
from datetime import UTC, datetime, timedelta

import pytest


def in_days(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def event_payload(**overrides) -> dict:
    return {
        "title": "Jazz Night",
        "description": "Live quartet",
        "venue": "Blue Hall",
        "starts_at": in_days(10),
        "ends_at": in_days(10.1),
        **overrides,
    }


async def create_event(client, headers, **overrides) -> dict:
    response = await client.post("/events", json=event_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def create_published_event(client, headers, **overrides) -> dict:
    event = await create_event(client, headers, **overrides)
    response = await client.post(f"/events/{event['id']}/publish", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- POST /events ---


async def test_organizer_creates_draft_event(client, organizer_headers):
    me = (await client.get("/users/me", headers=organizer_headers)).json()

    response = await client.post("/events", json=event_payload(), headers=organizer_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["organizer_id"] == me["id"]
    assert body["title"] == "Jazz Night"


async def test_customer_cannot_create_event(client, customer_headers):
    response = await client.post("/events", json=event_payload(), headers=customer_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_create_event_requires_login(client):
    response = await client.post("/events", json=event_payload())

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"ends_at": in_days(9)}, "INVALID_EVENT_TIMES"),  # ends before it starts
        ({"starts_at": in_days(-1), "ends_at": in_days(1)}, "INVALID_EVENT_TIMES"),  # in the past
    ],
)
async def test_create_event_rejects_bad_times(client, organizer_headers, changes, code):
    response = await client.post(
        "/events", json=event_payload(**changes), headers=organizer_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


async def test_create_event_rejects_datetime_without_timezone(client, organizer_headers):
    response = await client.post(
        "/events",
        json=event_payload(starts_at="2030-01-01T19:00:00", ends_at="2030-01-01T22:00:00"),
        headers=organizer_headers,
    )

    assert response.status_code == 422


# --- GET /events ---


async def test_list_shows_only_published_events(client, organizer_headers):
    published = await create_published_event(client, organizer_headers, title="Published")
    await create_event(client, organizer_headers, title="Draft")
    cancelled = await create_published_event(client, organizer_headers, title="Cancelled")
    await client.post(f"/events/{cancelled['id']}/cancel", headers=organizer_headers)

    response = await client.get("/events")

    assert response.status_code == 200
    body = response.json()
    assert [event["id"] for event in body["items"]] == [published["id"]]
    assert body["total"] == 1


async def test_list_paginates_in_start_order(client, organizer_headers):
    ids = []
    for day in (3, 1, 2):
        event = await create_published_event(
            client, organizer_headers, starts_at=in_days(day), ends_at=in_days(day + 0.1)
        )
        ids.append((day, event["id"]))
    ids_by_start = [event_id for _, event_id in sorted(ids)]

    response = await client.get("/events", params={"limit": 2, "offset": 1})

    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2 and body["offset"] == 1
    assert [event["id"] for event in body["items"]] == ids_by_start[1:]


async def test_list_filters_by_date_range(client, organizer_headers):
    await create_published_event(
        client, organizer_headers, starts_at=in_days(1), ends_at=in_days(1.1)
    )
    in_range = await create_published_event(
        client, organizer_headers, starts_at=in_days(5), ends_at=in_days(5.1)
    )
    await create_published_event(
        client, organizer_headers, starts_at=in_days(9), ends_at=in_days(9.1)
    )

    response = await client.get(
        "/events", params={"starts_after": in_days(4), "starts_before": in_days(6)}
    )

    assert [event["id"] for event in response.json()["items"]] == [in_range["id"]]


async def test_list_searches_title_description_and_venue(client, organizer_headers):
    by_title = await create_published_event(client, organizer_headers, title="Rock Fest")
    by_venue = await create_published_event(client, organizer_headers, venue="The Rock Arena")
    await create_published_event(client, organizer_headers, title="Opera", venue="Hall")

    response = await client.get("/events", params={"q": "rOcK"})

    found = {event["id"] for event in response.json()["items"]}
    assert found == {by_title["id"], by_venue["id"]}


async def test_list_rejects_too_large_limit(client):
    response = await client.get("/events", params={"limit": 500})

    assert response.status_code == 422


# --- GET /events/{id} ---


async def test_published_event_is_public(client, organizer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.get(f"/events/{event['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "published"


async def test_draft_is_visible_only_to_its_owner(
    client, organizer_headers, other_organizer_headers
):
    draft = await create_event(client, organizer_headers)
    url = f"/events/{draft['id']}"

    assert (await client.get(url)).status_code == 404
    assert (await client.get(url, headers=other_organizer_headers)).status_code == 404
    assert (await client.get(url, headers=organizer_headers)).status_code == 200


async def test_get_unknown_event_returns_404(client):
    response = await client.get(f"/events/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVENT_NOT_FOUND"


# --- PATCH /events/{id} ---


async def test_owner_updates_event(client, organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}",
        json={"title": "New Title", "venue": None},  # null means "leave unchanged"
        headers=organizer_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Title"
    assert body["venue"] == event["venue"]
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(event["updated_at"])


async def test_other_organizer_cannot_update_event(
    client, organizer_headers, other_organizer_headers
):
    event = await create_published_event(client, organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}", json={"title": "Hijacked"}, headers=other_organizer_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_customer_cannot_update_event(client, organizer_headers, customer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}", json={"title": "Nope"}, headers=customer_headers
    )

    assert response.status_code == 403


async def test_admin_can_update_any_event(client, organizer_headers, admin_headers):
    event = await create_event(client, organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}", json={"title": "Moderated"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Moderated"


async def test_update_rejects_end_before_start(client, organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}", json={"ends_at": in_days(1)}, headers=organizer_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_EVENT_TIMES"


async def test_cancelled_event_cannot_be_updated(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    response = await client.patch(
        f"/events/{event['id']}", json={"title": "Too late"}, headers=organizer_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_EVENT_STATUS"


# --- POST /events/{id}/publish and /cancel ---


async def test_publish_twice_is_rejected(client, organizer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.post(f"/events/{event['id']}/publish", headers=organizer_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_EVENT_STATUS"


async def test_other_organizer_cannot_publish(client, organizer_headers, other_organizer_headers):
    event = await create_event(client, organizer_headers)

    response = await client.post(f"/events/{event['id']}/publish", headers=other_organizer_headers)

    assert response.status_code == 403


async def test_owner_cancels_published_event(client, organizer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    # Cancelled events stay visible so ticket holders can see what happened.
    assert (await client.get(f"/events/{event['id']}")).json()["status"] == "cancelled"


async def test_cancel_twice_is_rejected(client, organizer_headers):
    event = await create_event(client, organizer_headers)
    await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    response = await client.post(f"/events/{event['id']}/cancel", headers=organizer_headers)

    assert response.status_code == 409


async def test_other_organizer_cannot_cancel(client, organizer_headers, other_organizer_headers):
    event = await create_published_event(client, organizer_headers)

    response = await client.post(f"/events/{event['id']}/cancel", headers=other_organizer_headers)

    assert response.status_code == 403
