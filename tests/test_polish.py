import json
import logging

from sqlalchemy import func, select

from app.core.config import Settings
from app.core.logging import JsonFormatter, request_id_var
from app.models.event import Event
from app.models.seat import Seat
from app.models.user import User
from app.services import events as event_service
from scripts.seed import seed
from tests.conftest import PASSWORD, TestSession
from tests.test_bookings import book, event_with_seats
from tests.test_payments import expire_hold

# --- one error shape for everything ---


async def test_validation_errors_use_the_error_shape(client):
    secret = "Xq7-zz"  # too short (< 8), and distinctive enough to search for
    response = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": secret, "full_name": "A"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["body", "password"]
    assert set(error["details"]["errors"][0]) == {"loc", "msg", "type"}
    assert secret not in response.text  # the rejected input is never echoed back


async def test_unknown_route_and_wrong_method_use_the_error_shape(client):
    not_found = await client.get("/nope")
    wrong_method = await client.delete("/health")

    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "NOT_FOUND"
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_unexpected_error_returns_500_without_internals(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(event_service, "list_published_events", boom)

    response = await client.get("/events")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
    assert response.headers["X-Request-ID"]


# --- request ids and logging ---


async def test_request_id_is_generated_or_echoed(client):
    generated = await client.get("/health")
    echoed = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    replaced = await client.get("/health", headers={"X-Request-ID": "bad id\twith spaces"})

    assert len(generated.headers["X-Request-ID"]) == 32
    assert echoed.headers["X-Request-ID"] == "abc-123"
    assert replaced.headers["X-Request-ID"] != "bad id\twith spaces"


async def test_every_request_is_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        await client.get("/health")

    [record] = [r for r in caplog.records if r.getMessage() == "request"]
    assert record.fields["method"] == "GET"
    assert record.fields["path"] == "/health"
    assert record.fields["status"] == 200
    assert record.fields["duration_ms"] >= 0


def test_log_lines_are_json_with_request_id():
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "hello", None, None)
    record.fields = {"status": 200}
    token = request_id_var.set("req-1")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert line["message"] == "hello"
    assert line["request_id"] == "req-1"
    assert line["status"] == 200
    assert line["level"] == "INFO"


# --- login rate limit ---


async def test_login_is_rate_limited_per_email(client, customer_headers):
    # customer_headers already logged in once (1 of 5 attempts).
    for _ in range(4):
        wrong = {"username": "customer@example.com", "password": "wrong-password"}
        assert (await client.post("/auth/login", data=wrong)).status_code == 401

    response = await client.post(
        "/auth/login", data={"username": "customer@example.com", "password": PASSWORD}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert 0 < int(response.headers["Retry-After"]) <= 60
    # Another email from the same client is not affected.
    other = await client.post("/auth/login", data={"username": "x@example.com", "password": "nope"})
    assert other.status_code == 401


# --- seat map shows expired holds as available ---


async def test_seat_map_shows_expired_hold_as_available(
    client, organizer_headers, customer_headers
):
    event, seats = await event_with_seats(client, organizer_headers, seats_per_row=2)
    expired = (await book(client, customer_headers, event, seats[:1])).json()
    await expire_hold(expired)
    await book(client, customer_headers, event, seats[1:2])

    seat_map = (await client.get(f"/events/{event['id']}/seats")).json()

    assert [seat["status"] for seat in seat_map] == ["available", "held"]


# --- seed script ---


async def test_seed_creates_demo_data_once():
    async with TestSession() as session:
        assert await seed(session, PASSWORD) is True
    async with TestSession() as session:
        assert await seed(session, PASSWORD) is False
        assert await session.scalar(select(func.count()).select_from(User)) == 3
        assert await session.scalar(select(func.count()).select_from(Event)) == 3
        assert await session.scalar(select(func.count()).select_from(Seat)) == 600 + 145 + 96


# --- settings ---


def test_database_url_gets_the_asyncpg_driver():
    secret = "x" * 32
    for given in ("postgresql://u:p@host/db", "postgres://u:p@host/db"):
        url = Settings(database_url=given, jwt_secret=secret).database_url
        assert url == "postgresql+asyncpg://u:p@host/db"
    already = "postgresql+asyncpg://u:p@host/db"
    assert Settings(database_url=already, jwt_secret=secret).database_url == already
