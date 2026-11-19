import asyncio
from sqlalchemy import String

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase       # нужна для транзакций
from sqlalchemy import URL, create_engine, text
from typing import Annotated

from src.config import settings

# Dependencies:
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

sync_engine = create_engine(
    url = settings.DATABASE_URL_psycopg,
    echo=True,
    pool_size=5,
    max_overflow=10,
)

async_engine = create_async_engine(
    url = settings.DATABASE_URL_asyncpg,
    echo=True,
    pool_size=5,
    max_overflow=10,
)

session_factory = sessionmaker(sync_engine)
async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

str_256 = Annotated[str, 256]
str_100 = Annotated[str, 100]
str_7 = Annotated[str, 100]

class Base(DeclarativeBase):
    type_annotation_map = {
        str_256: String(256),
        str_100: String(100),
        str_7: String(7),
    }


# Dependency for FastAPI
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session








