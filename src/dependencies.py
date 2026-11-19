from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.params import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import jwt as pyjwt
import os
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.queries.orm import ProjectsRepository, UsersRepository, TasksRepository, ProjectMembersRepository, \
    TaskAssigneeRepository
from src.models import UsersOrm, FilesOrm, TasksOrm, ProjectRole, ProjectsOrm, ROLE_RANK
from src.security import decode_access_token
from sqlalchemy import or_, select


bearer_scheme = HTTPBearer()

def _to_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

class Pagination:
    def __init__(self, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        session: AsyncSession = Depends(get_session)) -> UsersOrm:

    token = credentials.credentials
    try:
        user_id = decode_access_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await UsersRepository.get(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def project_file_paths(session: AsyncSession, project_id: int) -> list[str]:
    task_ids = select(TasksOrm.id).where(TasksOrm.project_id == project_id)
    stmt = select(FilesOrm.storage_path).where(
        or_(FilesOrm.project_id == project_id, FilesOrm.task_id.in_(task_ids)))
    return list(await session.scalars(stmt))

def remove_from_disk(paths: list[str]) -> None:
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# dependency members check
def project_access(min_role: ProjectRole = ProjectRole.viewer):
    async def dependency(project_id: int,
                         session: AsyncSession = Depends(get_session),
                         current_user: UsersOrm = Depends(get_current_user)) -> ProjectsOrm:
        await require_project_role(session, project_id, current_user.id, min_role)
        project = await ProjectsRepository.get(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    return dependency


async def get_task_access(session: AsyncSession,
                          task: TasksOrm,
                          user: UsersOrm) -> ProjectRole | None:
    if task.project_id is None:
        role = ProjectRole.owner if task.owner_id == user.id else None
    else:
        role = await ProjectMembersRepository.get_role(session, task.project_id, user.id)

    if role is None and await TaskAssigneeRepository.get_assignee(session, task.id, user.id):
        role = ProjectRole.viewer

    return role


def task_access(min_role: ProjectRole = ProjectRole.viewer):
    async def dependency(task_id: int,
                         session: AsyncSession = Depends(get_session),
                         current_user: UsersOrm = Depends(get_current_user)) -> tuple[TasksOrm, ProjectRole]:
        task = await TasksRepository.get(session, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        role = await get_task_access(session, task, current_user)
        if role is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if ROLE_RANK[role] < ROLE_RANK[min_role]:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return task, role
    return dependency

async def require_project_role(session: AsyncSession, project_id: int, user_id: int,
                               min_role: ProjectRole) -> ProjectRole:
    role = await ProjectMembersRepository.get_role(session, project_id, user_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return role

async def get_item_role(session: AsyncSession, item, user) -> ProjectRole | None:
    if getattr(item, "task_id", None) is not None:
        task = await TasksRepository.get(session, item.task_id)
        return await get_task_access(session, task, user) if task is not None else None
    if item.project_id is not None:
        return await ProjectMembersRepository.get_role(session, item.project_id, user.id)
    return ProjectRole.owner if item.owner_id == user.id else None


async def require_item_role(session: AsyncSession,
                            item, user: UsersOrm,
                            min_role: ProjectRole) -> ProjectRole:
    role = await get_item_role(session, item, user)
    if role is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return role
