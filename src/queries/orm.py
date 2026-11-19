import datetime
from typing import cast
from sqlalchemy import select, func, update, and_, or_, delete
from sqlalchemy.dialects.mssql.information_schema import constraints
from sqlalchemy.dialects.postgresql import insert as pg_insert   #   compromise to solve the "click-race"
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult
from src.database import sync_engine, async_engine, session_factory, async_session_factory, Base

from sqlalchemy.ext.asyncio import AsyncSession
from src.queries.base import BaseRepository, paginate, paginate_rows
from src.models import ProjectsOrm, UsersOrm, TasksOrm, StagesOrm, PlansOrm, PlanStatus, TaskStatus, NotesOrm, \
    FoldersOrm, \
    ProjectMembersOrm, ProjectRole, ContactsOrm, ContactsRequestsOrm, ContactsRequestsStatus, TaskAssigneesOrm

import bcrypt

from src.config import settings
from src.security import generate_refresh_token, hash_token
from src.models import RefreshTokensOrm, FilesOrm
from utils.gen_pub_id import generate_public_id


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def visible_to(model, user_id: int):
    my_projects = select(ProjectMembersOrm.project_id).where(ProjectMembersOrm.user_id == user_id)
    return or_(
        model.project_id.in_(my_projects),
        and_(model.project_id.is_(None), model.owner_id == user_id),
    )


class ProjectsRepository(BaseRepository[ProjectsOrm]):
    model = ProjectsOrm

    @staticmethod
    async def create(session: AsyncSession, owner_id: int, name: str,
                     description: str | None, color: str | None = None, due_date=None) -> ProjectsOrm:
        project = ProjectsOrm(owner_id=owner_id, name=name, description=description, color=color, due_date=due_date)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    @staticmethod   # deprecating
    async def list_by_owner(session: AsyncSession, owner_id: int, limit=100, offset=0) -> list[ProjectsOrm]:
        stmt = select(ProjectsOrm).where(ProjectsOrm.owner_id == owner_id)
        stmt = stmt.order_by(ProjectsOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: int, limit=100, offset=0) -> list[tuple[ProjectsOrm, ProjectRole]]:
        stmt = (select(ProjectsOrm, ProjectMembersOrm.role)
                .join(ProjectMembersOrm, ProjectMembersOrm.project_id == ProjectsOrm.id)
                .where(ProjectMembersOrm.user_id == user_id))
        stmt = stmt.order_by(ProjectsOrm.id).limit(limit).offset(offset)

        result = await session.execute(stmt)
        return result.all()     # unpack of Row and tuple is same


    @staticmethod
    async def get_owned(session: AsyncSession, project_id: int, owner_id: int) -> ProjectsOrm | None:
        stmt = select(ProjectsOrm).where(ProjectsOrm.id == project_id, ProjectsOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()


class UsersRepository(BaseRepository[UsersOrm]):
    model = UsersOrm

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> UsersOrm | None:
        stmt = select(UsersOrm).where(UsersOrm.email == email)
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def get_by_public_id(session: AsyncSession, public_id: str) -> UsersOrm | None:
        stmt = select(UsersOrm).where(UsersOrm.public_id == public_id)
        return (await session.scalars(stmt)).first()

    @staticmethod
    async def create(session: AsyncSession, email: str, password: str,
                     display_name: str | None = None, ) -> UsersOrm | None:
        for _ in range(5):
            user = UsersOrm(email=email, password_hash=hash_password(password),
                            display_name=display_name, public_id=generate_public_id())
            try:
                async with session.begin_nested():  # savepoint per try
                    session.add(user)
                    await session.flush()           # find collision if exists
                break                               # paste to DB is done
            except IntegrityError as e:
                constraint = getattr(e.orig.__cause__, "constraint_name", None)

                if constraint == "uq_users_email":
                    return None

                if constraint not in ("uq_users_public_id", "users_public_id_key"):
                    raise
        else:
            raise RuntimeError("Could not issue ID..")

        await session.commit()
        await session.refresh(user)
        return user


# userspace work functionality
class TasksRepository(BaseRepository):
    model = TasksOrm

    @staticmethod
    async def list_visible(session: AsyncSession, user_id: int, project_id: int | None = None,
                           assigned_to_me: bool = False, limit=100, offset=0):
        my_projects = select(ProjectMembersOrm.project_id).where(ProjectMembersOrm.user_id==user_id)
        my_assignees = select(TaskAssigneesOrm.task_id).where(TaskAssigneesOrm.user_id == user_id)
        stmt = select(TasksOrm).where(
            or_(
                and_(TasksOrm.project_id.is_(None), TasksOrm.owner_id==user_id),
                TasksOrm.project_id.in_(my_projects),
                TasksOrm.id.in_(my_assignees),
            )
        )
        if project_id is not None:
            stmt = stmt.where(TasksOrm.project_id == project_id)
        if assigned_to_me:
            stmt = stmt.where(TasksOrm.id.in_(my_assignees))

        stmt = stmt.order_by(TasksOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def create(session: AsyncSession, owner_id: int, title: str, description: str | None,
                     project_id: int | None, stage_id: int | None = None,
                     parent_task_id: int | None = None, due_date=None, priority: int = 0, commit: bool = True) -> TasksOrm:
        task = TasksOrm(
            owner_id=owner_id, title=title, description=description, project_id=project_id,
            stage_id=stage_id, parent_task_id=parent_task_id, due_date=due_date, priority=priority,
        )
        session.add(task)
        await session.flush()
        if commit:
            await session.commit()
            await session.refresh(task)
        return task

    @staticmethod
    async def get_owned(session: AsyncSession, task_id: int, owner_id: int) -> TasksOrm | None:
        stmt = select(TasksOrm).where(TasksOrm.id == task_id, TasksOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def list_by_owner(session: AsyncSession, owner_id: int, project_id: int | None = None, limit=100, offset=0) -> list[TasksOrm]:
        stmt = select(TasksOrm).where(TasksOrm.owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(TasksOrm.project_id == project_id)
        stmt = stmt.order_by(TasksOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def get_progress(session: AsyncSession, project_id: int) -> dict:
        stmt = (
            select(
                func.count(TasksOrm.id).filter(TasksOrm.status != TaskStatus.cancelled).label("total"),
                func.count(TasksOrm.id).filter(TasksOrm.status == TaskStatus.done).label("completed"),
            )
            .where(TasksOrm.project_id == project_id)
        )
        row = (await session.execute(stmt)).one()
        total, completed = row.total, row.completed
        progress_pct = round(completed / total * 100, 2) if total > 0 else 0.0
        return {"total_tasks": total, "completed_tasks": completed, "progress_pct": progress_pct}

    @classmethod
    async def update(cls, session: AsyncSession, task: TasksOrm, updates: dict) -> TasksOrm:
        updates = dict(updates)
        if "status" in updates and updates["status"] != task.status:
            updates["completed_at"] = datetime.datetime.now(datetime.UTC) if updates["status"] == TaskStatus.done else None
        return await super().update(session, task, updates)


class PlansRepository(BaseRepository):
    model = PlansOrm

    @staticmethod
    async def create(session: AsyncSession, owner_id: int, title: str, description: str | None, due_date=None) -> PlansOrm:
        plan = PlansOrm(owner_id=owner_id, title=title, description=description, due_date=due_date)
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    async def get_owned(session: AsyncSession, plan_id: int, owner_id: int) -> PlansOrm | None:
        stmt = select(PlansOrm).where(PlansOrm.id == plan_id, PlansOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def list_by_owner(session: AsyncSession, owner_id: int, limit=100, offset=0) -> list[PlansOrm]:
        stmt = select(PlansOrm).where(PlansOrm.owner_id == owner_id)
        stmt = stmt.order_by(PlansOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def convert_to_task(session: AsyncSession, plan: PlansOrm) -> TasksOrm:
        task = TasksOrm(owner_id=plan.owner_id, title=plan.title, description=plan.description, due_date=plan.due_date)
        session.add(task)
        await session.flush() # no commit already, it sends INSERT and get task.id, but still not yield transaction

        plan.status = PlanStatus.converted
        plan.converted_to_task_id = task.id

        await session.commit()
        await session.refresh(task)
        return task

    @staticmethod
    async def convert_to_project(session: AsyncSession, plan: PlansOrm) -> ProjectsOrm:
        project = ProjectsOrm(owner_id=plan.owner_id, name=plan.title, description=plan.description,
                              due_date=plan.due_date)
        session.add(project)
        await session.flush()   # get project_id without commit

        plan.status = PlanStatus.converted
        plan.converted_to_project_id = project.id

        session.add(ProjectMembersOrm(project_id=project.id, user_id=plan.owner_id, role=ProjectRole.owner))

        await session.commit()
        await session.refresh(project)
        return project


# Progress
class StagesRepository(BaseRepository):
    model = StagesOrm

    @staticmethod
    async def create(session: AsyncSession, project_id: int, name: str, description: str | None = None,
                     due_date = None, order_index: int = 0) -> StagesOrm:
        stage = StagesOrm(project_id=project_id, name=name, description=description, due_date=due_date, order_index=order_index)
        session.add(stage)
        await session.commit()
        await session.refresh(stage)
        return stage

    @staticmethod
    async def list_by_project(session: AsyncSession, project_id: int) -> list[StagesOrm]:
        stmt = select(StagesOrm).where(StagesOrm.project_id == project_id).order_by(StagesOrm.order_index)
        result = await session.scalars(stmt)
        return list(result)

    @staticmethod
    async def get_by_project(session: AsyncSession, stage_id: int, project_id: int) -> StagesOrm | None:
        stmt = select(StagesOrm).where(StagesOrm.id == stage_id, StagesOrm.project_id == project_id)
        result = await session.scalars(stmt)
        return result.first()


class FoldersRepository(BaseRepository[FoldersOrm]):
    model = FoldersOrm

    @staticmethod
    async def create(session, owner_id, name, parent_folder_id=None, project_id=None):
        folder = FoldersOrm(owner_id=owner_id, name=name, parent_folder_id=parent_folder_id, project_id=project_id)
        session.add(folder)
        await session.commit()
        await session.refresh(folder)
        return folder

    @staticmethod
    async def get_owned(session, folder_id, owner_id):
        stmt = select(FoldersOrm).where(FoldersOrm.id == folder_id, FoldersOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def list_by_owner(session, owner_id, project_id=None, parent_folder_id=None, limit=100, offset=0):
        stmt = select(FoldersOrm).where(FoldersOrm.owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(FoldersOrm.project_id == project_id)
        if parent_folder_id is not None:
            stmt = stmt.where(FoldersOrm.parent_folder_id == parent_folder_id)
        stmt = stmt.order_by(FoldersOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def would_create_cycle(session: AsyncSession, folder_id: int, new_parent_id: int) -> bool:
        current, seen = new_parent_id, set()
        while current is not None and current not in seen:
            if current == folder_id:
                return True
            seen.add(current)
            current = await session.scalar(
                select(FoldersOrm.parent_folder_id).where(FoldersOrm.id == current)
            )
        return False

    @staticmethod
    async def list_visible(session, user_id: int, parent_folder_id: int | None = None,
                           project_id: int | None = None, limit=100, offset=0):
        stmt = select(FoldersOrm).where(visible_to(FoldersOrm, user_id))
        if project_id is not None:
            stmt = stmt.where(FoldersOrm.project_id == project_id)
        if parent_folder_id is not None:
            stmt = stmt.where(FoldersOrm.parent_folder_id == parent_folder_id)
        stmt = stmt.order_by(FoldersOrm.id)
        return await paginate(session, stmt, limit, offset)


class NotesRepository(BaseRepository[NotesOrm]):
    model = NotesOrm

    @staticmethod
    async def create(session, owner_id, content, title=None, folder_id=None, project_id=None, task_id=None):
        note = NotesOrm(owner_id=owner_id, content=content, title=title, folder_id=folder_id, project_id=project_id, task_id=task_id)
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return note

    @staticmethod
    async def list_by_owner(session, owner_id, folder_id=None, project_id=None, task_id=None, limit=100, offset=0):
        stmt = select(NotesOrm).where(NotesOrm.owner_id == owner_id)
        if folder_id is not None:
            stmt = stmt.where(NotesOrm.folder_id == folder_id)
        if project_id is not None:
            stmt = stmt.where(NotesOrm.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(NotesOrm.task_id == task_id)
        stmt = stmt.order_by(NotesOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def list_visible(session, user_id, folder_id: int | None = None, project_id: int | None = None,
                           task_id: int | None = None, limit=100, offset=0):
        stmt = select(NotesOrm).where(visible_to(NotesOrm, user_id))
        if folder_id is not None:
            stmt = stmt.where(NotesOrm.folder_id == folder_id)
        if project_id is not None:
            stmt = stmt.where(NotesOrm.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(NotesOrm.task_id == task_id)
        stmt = stmt.order_by(NotesOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def get_owned(session, note_id, owner_id):
        stmt = select(NotesOrm).where(NotesOrm.id == note_id, NotesOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()


class RefreshTokensRepository(BaseRepository[RefreshTokensOrm]):
    model = RefreshTokensOrm

    @staticmethod
    async def create(session: AsyncSession, user_id: int) -> str:
        raw_token = generate_refresh_token()
        expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        rt = RefreshTokensOrm(user_id=user_id, token_hash=hash_token(raw_token), expires_at=expires_at)
        session.add(rt)
        await session.commit()
        return raw_token     # the database has a hash, but the calling code needs a raw token — not to get it back

    @staticmethod
    async def get_valid(session: AsyncSession, token_hash: str) -> RefreshTokensOrm | None:
        stmt = select(RefreshTokensOrm).where(
            RefreshTokensOrm.token_hash == token_hash,
            RefreshTokensOrm.revoked_at.is_(None),
            RefreshTokensOrm.expires_at > datetime.datetime.now(datetime.UTC),
        )
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def revoke(session: AsyncSession, token_obj: RefreshTokensOrm) -> None:
        token_obj.revoked_at = datetime.datetime.now(datetime.UTC)
        await session.commit()

    @staticmethod
    async def revoke_all(session: AsyncSession, user_id: int) -> None:
        stmt = (update(RefreshTokensOrm)
                .where(RefreshTokensOrm.user_id == user_id, RefreshTokensOrm.revoked_at.is_(None))
                .values(revoked_at=datetime.datetime.now(datetime.UTC)))
        await session.execute(stmt)
        await session.commit()


class FilesRepository(BaseRepository[FilesOrm]):
    model = FilesOrm

    @staticmethod
    async def create(session, owner_id, filename, storage_path, mime_type=None,
                      size_bytes=None, project_id=None, task_id=None):
        file_obj = FilesOrm(owner_id=owner_id, filename=filename, storage_path=storage_path,
                            mime_type=mime_type, size_bytes=size_bytes,
                            project_id=project_id, task_id=task_id)
        session.add(file_obj)
        await session.commit()
        await session.refresh(file_obj)
        return file_obj

    @staticmethod
    async def get_owned(session, file_id, owner_id):
        stmt = select(FilesOrm).where(FilesOrm.id == file_id, FilesOrm.owner_id == owner_id)
        result = await session.scalars(stmt)
        return result.first()

    @staticmethod
    async def list_by_owner(session, owner_id, project_id=None, limit=100, offset=0):
        stmt = select(FilesOrm).where(FilesOrm.owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(FilesOrm.project_id == project_id)
        stmt = stmt.order_by(FilesOrm.id)
        return await paginate(session, stmt, limit, offset)

    @staticmethod
    async def list_visible(session, user_id: int, project_id: int | None = None,
                           limit=100, offset=0):
        stmt = select(FilesOrm).where(visible_to(FilesOrm, user_id))

        if project_id is not None:
            stmt = stmt.where(FilesOrm.project_id == project_id)

        stmt = stmt.order_by(FilesOrm.id)
        return await paginate(session, stmt, limit, offset)


class ProjectMembersRepository(BaseRepository[ProjectMembersOrm]):
    model = ProjectMembersOrm

    @staticmethod
    async def get_role(session: AsyncSession, project_id: int, user_id: int) -> ProjectRole | None:
        stmt = select(ProjectMembersOrm.role).where(
            ProjectMembersOrm.project_id == project_id, ProjectMembersOrm.user_id == user_id
        )
        return await session.scalar(stmt)

    @staticmethod
    async def add(session: AsyncSession, project_id: int, user_id: int, role: ProjectRole) -> ProjectMembersOrm:
        member = ProjectMembersOrm(project_id=project_id, user_id=user_id, role=role)
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member

    @staticmethod
    async def add_many(session: AsyncSession, project_id: int, members: list[tuple[int, ProjectRole]],
                       commit: bool = True) -> None:
        session.add_all([ProjectMembersOrm(project_id=project_id, user_id=uid, role=role) for uid, role in members])
        if commit:
            await session.commit()

    @staticmethod
    async def list_members(session: AsyncSession, project_id: int) -> list[tuple[ProjectMembersOrm, UsersOrm]]:
        stmt = (select(ProjectMembersOrm, UsersOrm)
                .join(UsersOrm, UsersOrm.id == ProjectMembersOrm.user_id)
                .where(ProjectMembersOrm.project_id==project_id))
        return (await session.execute(stmt)).all()

    @staticmethod
    async def get_member(session: AsyncSession, project_id: int, user_id: int) -> ProjectMembersOrm | None:
        stmt = (select(ProjectMembersOrm)
                .where(ProjectMembersOrm.project_id == project_id,
                       ProjectMembersOrm.user_id == user_id))
        return (await session.scalars(stmt)).first()

    @staticmethod
    async def count_owners(session: AsyncSession, project_id: int) -> int:
        stmt = ((select(ProjectMembersOrm.id)
                .where(ProjectMembersOrm.project_id == project_id,
                       ProjectMembersOrm.role == ProjectRole.owner))
                .with_for_update())     # if it's concurrent the second one will wait before commit
        return len((await session.scalars(stmt)).all())


class ContactsRequestsRepository(BaseRepository[ContactsRequestsOrm]):
    model = ContactsRequestsOrm

    @staticmethod
    async def get_pending(session: AsyncSession, from_id: int, to_id: int) -> ContactsRequestsOrm | None:
        stmt = select(ContactsRequestsOrm).where(
            ContactsRequestsOrm.from_id == from_id,
            ContactsRequestsOrm.to_id == to_id,
            ContactsRequestsOrm.status == "pending"
        )
        return (await session.scalars(stmt)).first()

    @staticmethod
    async def accept_invite(session: AsyncSession, request: ContactsRequestsOrm) -> None:
        request.status = ContactsRequestsStatus.accepted
        request.responded_at = datetime.datetime.now(datetime.UTC)

        session.add_all([
            ContactsOrm(owner_id=request.from_id, contact_id=request.to_id),
            ContactsOrm(owner_id=request.to_id, contact_id=request.from_id),
        ])
        await session.commit()

    @staticmethod
    async def declined_recently(session: AsyncSession, current_user_id: int, target_user_id: int, hours=1) -> bool:
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
        line = select(ContactsRequestsOrm).where(
            ContactsRequestsOrm.from_id == current_user_id,
            ContactsRequestsOrm.to_id == target_user_id,
            ContactsRequestsOrm.status == ContactsRequestsStatus.declined,
            ContactsRequestsOrm.responded_at > since,
        ).limit(1)
        return (await session.scalars(line)).first() is not None

    @staticmethod
    async def create_request(session: AsyncSession, user_id: int, contact_id: int) -> None:
        request = ContactsRequestsOrm(from_id=user_id, to_id=contact_id)
        session.add(request)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            if "uq_constraint_requests_pending" in str(e.orig):
                raise

    @staticmethod
    async def request_list(session: AsyncSession, owner_id: int) -> list[tuple[ContactsRequestsOrm, UsersOrm]]:
        stmt = (select(ContactsRequestsOrm, UsersOrm)
                .join(UsersOrm, UsersOrm.id == ContactsRequestsOrm.from_id)
                .where(ContactsRequestsOrm.to_id == owner_id,
                       ContactsRequestsOrm.status == ContactsRequestsStatus.pending)
                .order_by(ContactsRequestsOrm.id)
                )
        return (await session.execute(stmt)).all()

    @staticmethod
    async def decline_request(session: AsyncSession, request: ContactsRequestsOrm) -> None:
        request.status = ContactsRequestsStatus.declined
        request.responded_at = datetime.datetime.now(datetime.UTC)

        await session.commit()

    @staticmethod
    async def cancel_request(session: AsyncSession, request: ContactsRequestsOrm) -> None:
        request.status = ContactsRequestsStatus.cancelled
        request.responded_at = datetime.datetime.now(datetime.UTC)

        await session.commit()


class ContactsRepository(BaseRepository[ContactsOrm]):
    model = ContactsOrm

    @staticmethod
    async def exist_in_contacts(session: AsyncSession, owner_id: int, contact_id: int) -> bool:
        return await session.get(ContactsOrm, (owner_id, contact_id)) is not None

    @staticmethod
    async def get_contact_list(session: AsyncSession, owner_id: int, limit: int=100, offset: int=0):
        stmt = (select(ContactsOrm, UsersOrm)
                .join(UsersOrm, UsersOrm.id == ContactsOrm.contact_id)
                .where(ContactsOrm.owner_id == owner_id)
                .order_by(ContactsOrm.created_at))
        return await paginate_rows(session, stmt, limit, offset)

    @staticmethod
    async def get_contact(session: AsyncSession, owner_id: int, contact_id: int) -> ContactsOrm | None:
        return await session.get(ContactsOrm, (owner_id, contact_id))

    @staticmethod
    async def contact_delete(session: AsyncSession, owner_id: int, contact_id: int) -> int:
        stmt = (delete(ContactsOrm)
                .where(or_(
                    and_(ContactsOrm.owner_id==owner_id, ContactsOrm.contact_id==contact_id),
                    and_(ContactsOrm.owner_id==contact_id, ContactsOrm.contact_id==owner_id),
                )))
        result = cast(CursorResult, await session.execute(stmt))
        await session.commit()
        return result.rowcount  # noqa

    @staticmethod
    async def get_contacts_by_public_ids(session: AsyncSession, owner_id: int, public_ids: list[str]) -> list[UsersOrm]:
        stmt = (select(UsersOrm)
                .join(
                    ContactsOrm, ContactsOrm.contact_id == UsersOrm.id)
                    .where(ContactsOrm.owner_id == owner_id,
                           UsersOrm.public_id.in_(public_ids))
        )
        return list((await session.scalars(stmt)).all())


class TaskAssigneeRepository(BaseRepository[TaskAssigneesOrm]):

    @staticmethod
    async def get_assignee(session: AsyncSession, task_id: int, user_id: int) -> TaskAssigneesOrm | None:
        stmt = (select(TaskAssigneesOrm)
                .where(TaskAssigneesOrm.task_id == task_id,
                       TaskAssigneesOrm.user_id == user_id))
        return await session.scalar(stmt)

    @staticmethod
    async def make_assignee(session: AsyncSession, task_id: int, user_ids: list[int]) -> None:
        pass


    @staticmethod
    async def add_many_assignees(session: AsyncSession, task_id: int, user_ids: list[int],
                                 assigned_by_id: int, commit: bool = True) -> None:
        if not user_ids:
            return
        stmt = (pg_insert(TaskAssigneesOrm)
                .values([{"task_id": task_id, "user_id":uid, "assigned_by_id":assigned_by_id} for uid in user_ids])
                .on_conflict_do_nothing(constraint="uq_task_member"))
        await session.execute(stmt)
        if commit:
            await session.commit()

    @staticmethod
    async def assignee_mark_done(session: AsyncSession, assignee: TaskAssigneesOrm,
                                 done_note: str | None = None) -> None:
        assignee.done_at = datetime.datetime.now(datetime.UTC)
        if done_note:
            assignee.done_note = done_note
        await session.commit()

    @staticmethod
    async def list_assignees(session: AsyncSession, task_id: int) -> list[tuple[TaskAssigneesOrm, UsersOrm]]:
        stmt = (select(TaskAssigneesOrm, UsersOrm)
                .join(UsersOrm, UsersOrm.id == TaskAssigneesOrm.user_id)
                .where(TaskAssigneesOrm.task_id == task_id)
                .order_by(TaskAssigneesOrm.id))

        result = await session.execute(stmt)
        return result.all()

    @staticmethod
    async def unmark_assign(session: AsyncSession, assignee: TaskAssigneesOrm, reject_note: str | None = None) -> None:
        assignee.done_at = None
        if reject_note:
            assignee.return_note = reject_note
        await session.commit()

    @staticmethod
    async def change_assignee_note(session: AsyncSession, assignee: TaskAssigneesOrm, done_note: str | None = None) -> None:
        assignee.done_note = done_note
        await session.commit()

    @staticmethod
    async def change_reject_note(session: AsyncSession, assignee: TaskAssigneesOrm, return_note: str | None = None) -> None:
        assignee.return_note = return_note
        await session.commit()

    @staticmethod
    async def assign_delete(session: AsyncSession, task_id: int, user_id: int) -> None:
        stmt = (delete(TaskAssigneesOrm)
                .where(TaskAssigneesOrm.task_id == task_id,
                       TaskAssigneesOrm.user_id == user_id)
                )
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def reject_assign_done(session: AsyncSession, task_id, user_id: int, assigned_by_id: int):
        pass










