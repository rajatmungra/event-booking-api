import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.rate_limit import login_limiter
from app.core.security import password_hash
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.user import User, UserRole

assert settings.test_database_url, "Set TEST_DATABASE_URL (see .env.example) to run the tests."

# NullPool opens a fresh connection per session, so no connection is shared between the
# event loops that pytest-asyncio creates for each test.
test_engine = create_async_engine(settings.test_database_url, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def create_schema():
    async def reset():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())


@pytest.fixture(autouse=True)
def reset_login_limiter():
    # The limiter lives in memory for the whole test run; start every test with a clean slate.
    login_limiter.attempts.clear()


@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    # Real commits + TRUNCATE (instead of rolling back each test) so concurrency tests
    # can use several independent transactions.
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


async def get_test_session():
    async with TestSession() as session:
        yield session


@pytest.fixture
async def client():
    app.dependency_overrides[get_session] = get_test_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def login_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", data={"username": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def register_and_login(client: AsyncClient, email: str, role: str) -> dict[str, str]:
    await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Test User", "role": role},
    )
    return await login_headers(client, email)


@pytest.fixture
async def customer_headers(client):
    return await register_and_login(client, "customer@example.com", "customer")


@pytest.fixture
async def organizer_headers(client):
    return await register_and_login(client, "organizer@example.com", "organizer")


@pytest.fixture
async def other_organizer_headers(client):
    return await register_and_login(client, "other-organizer@example.com", "organizer")


@pytest.fixture
async def admin_headers(client):
    # Admins can't self-register, so insert one directly.
    async with TestSession() as session:
        session.add(
            User(
                email="admin@example.com",
                hashed_password=password_hash.hash(PASSWORD),
                full_name="Admin",
                role=UserRole.admin,
            )
        )
        await session.commit()
    return await login_headers(client, "admin@example.com")
