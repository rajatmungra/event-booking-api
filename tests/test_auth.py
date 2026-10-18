import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.api.deps import require_role
from app.core.config import settings
from app.core.exceptions import PermissionDenied
from app.core.security import ALGORITHM
from app.models.user import User, UserRole
from tests.conftest import PASSWORD

NEW_USER = {"email": "Alice@Example.com", "password": PASSWORD, "full_name": "Alice"}


# --- register ---


async def test_register_creates_customer(client):
    response = await client.post("/auth/register", json=NEW_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "customer"
    assert body["is_active"] is True
    assert "hashed_password" not in body and "password" not in body


async def test_register_as_organizer(client):
    response = await client.post("/auth/register", json={**NEW_USER, "role": "organizer"})

    assert response.status_code == 201
    assert response.json()["role"] == "organizer"


async def test_register_duplicate_email_is_rejected(client):
    await client.post("/auth/register", json=NEW_USER)

    # Same address with different casing still counts as a duplicate.
    response = await client.post("/auth/register", json={**NEW_USER, "email": "alice@EXAMPLE.com"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"full_name": ""},
        {"role": "admin"},
    ],
)
async def test_register_rejects_invalid_input(client, changes):
    response = await client.post("/auth/register", json={**NEW_USER, **changes})

    assert response.status_code == 422


# --- login ---


async def test_login_returns_access_token(client):
    await client.post("/auth/register", json=NEW_USER)

    response = await client.post(
        "/auth/login", data={"username": "alice@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(client):
    await client.post("/auth/register", json=NEW_USER)

    response = await client.post(
        "/auth/login", data={"username": "alice@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email(client):
    response = await client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


# --- /users/me (protected route) ---


async def test_me_returns_current_user(client, customer_headers):
    response = await client.get("/users/me", headers=customer_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "customer@example.com"


async def test_me_without_token(client):
    response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_with_invalid_token(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_with_expired_token(client, customer_headers):
    me = (await client.get("/users/me", headers=customer_headers)).json()
    expired = jwt.encode(
        {"sub": me["id"], "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


# --- require_role ---


def make_user(role: UserRole) -> User:
    return User(id=uuid.uuid4(), email="x@example.com", role=role, is_active=True)


async def test_require_role_allows_matching_role():
    check = require_role(UserRole.organizer)

    user = make_user(UserRole.organizer)

    assert await check(user) is user


async def test_require_role_allows_admin_for_any_role():
    check = require_role(UserRole.organizer)

    user = make_user(UserRole.admin)

    assert await check(user) is user


async def test_require_role_rejects_other_role():
    check = require_role(UserRole.organizer)

    with pytest.raises(PermissionDenied):
        await check(make_user(UserRole.customer))


async def test_admin_can_log_in(client, admin_headers):
    response = await client.get("/users/me", headers=admin_headers)

    assert response.json()["role"] == "admin"
