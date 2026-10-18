import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_session
from app.main import app


@pytest.fixture
def client():
    # The `with` block keeps one event loop for the whole test, which asyncpg connections need.
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_503_when_db_unreachable(client):
    # Nothing listens on port 1, so connecting fails immediately.
    engine = create_async_engine("postgresql+asyncpg://user:pass@127.0.0.1:1/none")

    async def unreachable_session():
        async with async_sessionmaker(engine)() as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
