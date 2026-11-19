from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
from typing import Any

from src.database import get_session
from src.dependencies import get_current_user, _to_naive_utc
from src.models import UsersOrm
from src.schemas import CalendarItemRead


router = APIRouter()

@router.get("/calendar", response_model=list[CalendarItemRead])
async def get_calendar(
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        current_user: UsersOrm = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    params: dict[str, Any] = {"user_id": current_user.id}  # typification

    query = "SELECT item_type, id, title, due_date FROM calendar_items WHERE user_id = :user_id"
    params = {"user_id": current_user.id}
    if date_from is not None:
        query += " AND due_date >= :date_from"
        params["date_from"] = _to_naive_utc(date_from)
    if date_to is not None:
        query += " AND due_date <= :date_to"
        params["date_to"] = _to_naive_utc(date_to)
    query += " ORDER BY due_date"

    result = await session.execute(text(query), params)
    return [dict(row) for row in result.mappings()]         # or [dict(row._mapping) for row in result]
