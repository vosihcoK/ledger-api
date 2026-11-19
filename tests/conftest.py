import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.database import Base, get_session
from src.config import settings
from src.models import UsersOrm

TEST_DATABASE_URL = settings.DATABASE_URL_asyncpg.rsplit("/", 1)[0] + "/alembic_test"

engine_test = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
async_session_test = async_sessionmaker(engine_test, expire_on_commit=False)


async def override_get_session():
    async with async_session_test() as session:
        yield session

# change app DB for test
app.dependency_overrides[get_session] = override_get_session


pytest_plugins = [
    "tests.fixtures.contacts",
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture(scope="session")
async def create_user(client):
    async def _make(email: str, password: str = "secret123"):
        response = await client.post("/users", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()
    return _make


@pytest_asyncio.fixture(scope="session")
async def _get_auth_headers(client):
    async def _make(email: str, password: str = "secret123") -> dict:
        resp = await client.post("/login", json={"email": email, "password": password})
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _make

@pytest_asyncio.fixture
async def create_project(client):
    async def _make(headers: dict, name: str = "Project", **extra) -> dict:
        resp = await client.post("/projects", json={"name": name, **extra}, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()
    return _make


@pytest_asyncio.fixture
async def create_task(client):
    async def _make(headers: dict, title: str = "Task!", **extra) -> dict:
        resp = await client.post("/tasks", json={"title": title, **extra}, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()
    return _make


@pytest_asyncio.fixture(scope="session")
async def users(create_user, _get_auth_headers):
    headers_by_user = {}

    async with async_session_test() as session:
        for n in range(1,6):
            name = f"user_{n}"
            email = f"{name}@test.com"
            await create_user(email)
            row = await session.scalar(select(UsersOrm).where(UsersOrm.email==email))
            assert row is not None, f"Не найдена учетная запись для {email}"
            headers_by_user[name] = {"headers": await _get_auth_headers(email), "row": row}

    return headers_by_user




