from typing import TypeVar, Generic
from sqlalchemy import select, func, Select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Base

ModelType = TypeVar("ModelType", bound=Base)


async def paginate_rows(session: AsyncSession, stmt: Select, limit: int, offset: int):
    counted = stmt.order_by(None).subquery()
    total = await session.scalar(select(func.count()).select_from(counted))
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
    return rows, total


async def paginate(session: AsyncSession, stmt, limit: int, offset: int):
    counted = stmt.order_by(None).subquery()
    total = await session.scalar(select(func.count()).select_from(counted))
    items = await session.scalars(stmt.limit(limit).offset(offset))
    return list(items), total

class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    @classmethod
    async def get(cls, session: AsyncSession, id: int) -> ModelType | None:
        return await session.get(cls.model, id)

    @classmethod
    async def list_all(cls, session: AsyncSession) -> list[ModelType]:
        result = await session.scalars(select(cls.model))
        return list(result)

    @classmethod
    async def delete(cls, session: AsyncSession, id: int) -> None:
        obj = await session.get(cls.model, id)
        if obj:
            await session.delete(obj)
            await session.commit()

    @classmethod
    async def update(cls, session: AsyncSession, obj: ModelType, updates: dict) -> ModelType:
        for key, value in updates.items():
            setattr(obj, key, value)
        await session.commit()
        await session.refresh(obj)
        return obj
