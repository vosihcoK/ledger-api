from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.dependencies import get_current_user, require_project_role, get_task_access, Pagination, remove_from_disk, \
    task_access
from src.models import UsersOrm, FilesOrm, TasksOrm, ProjectRole, TaskStatus
from src.queries.orm import StagesRepository, TasksRepository, ContactsRepository, TaskAssigneeRepository, \
    UsersRepository
from src.schemas import TaskRead, TaskCreate, TaskUpdate, TaskAssigneeMarkDone, TaskAssigneeRead, PublicUser, \
    TaskAssigneesAdd, TaskAssigneeReject

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", response_model=TaskRead)
async def create_task(
        payload: TaskCreate,
        current_user: UsersOrm = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if payload.project_id is not None:
        await require_project_role(session, payload.project_id, current_user.id, ProjectRole.editor)


    if payload.stage_id is not None:
        if payload.project_id is None:
            raise HTTPException(status_code=400, detail="stage_id requires project_id")
        stage = await StagesRepository.get_by_project(session, payload.stage_id, payload.project_id)
        if stage is None:
            raise HTTPException(status_code=404, detail="Stage not found in this project")

    if payload.parent_task_id is not None:
        parent = await TasksRepository.get(session, payload.parent_task_id)
        if parent is None or await get_task_access(session, parent, current_user) is None:
            raise HTTPException(status_code=404, detail="Parent task not found")
        if parent.project_id != payload.project_id:
            raise HTTPException(status_code=400, detail="Subtask must belong to the same project as its parent")

    public_ids = {i.public_id for i in payload.assignees}

    self_todo = current_user.public_id in public_ids
    public_ids.discard(current_user.public_id)

    wanted = await ContactsRepository.get_contacts_by_public_ids(session, current_user.id, list(public_ids))
    if len(wanted) != len(public_ids):
        raise HTTPException(status_code=409, detail="Contact not found")

    task = await TasksRepository.create(session, title=payload.title, owner_id=current_user.id,
                                  description=payload.description,project_id=payload.project_id,
                                  stage_id=payload.stage_id, parent_task_id=payload.parent_task_id,
                                  due_date=payload.due_date, priority=payload.priority, commit=False)
    user_ids = [u.id for u in wanted]
    if self_todo:
        user_ids.append(current_user.id)
    await TaskAssigneeRepository.add_many_assignees(session, task.id, user_ids, current_user.id, commit=False)

    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
        response: Response,
        project_id: int | None = None,
        assigned_to_me: bool = False,
        page: Pagination = Depends(),
        current_user: UsersOrm = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    items, total = await TasksRepository.list_visible(
        session, current_user.id, project_id, assigned_to_me, page.limit, page.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
                      payload: TaskUpdate,
                      access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.editor)),
                      session: AsyncSession = Depends(get_session),
                      ):
    task, role = access
    updates = payload.model_dump(exclude_unset=True)

    # make the task is done can just owner
    if updates.get("status") == TaskStatus.done and task.status != TaskStatus.done and role != ProjectRole.owner:
        raise HTTPException(status_code=403, detail="Only the owner can close the task")

    new_stage_id = updates.get("stage_id")

    if new_stage_id is not None:
        if task.project_id is None:
            raise HTTPException(status_code=400, detail="Task has no project, stage cannot be set")
        stage = await StagesRepository.get_by_project(session, new_stage_id, task.project_id)
        if stage is None:
            raise HTTPException(status_code=404, detail="Stage not found in this project")
    return await TasksRepository.update(session, task, updates)


@router.delete("/{task_id}", status_code=204)
async def delete_task(access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.owner)),
                      session: AsyncSession = Depends(get_session)):
    task, _ = access
    paths = list(await session.scalars(select(FilesOrm.storage_path).where(FilesOrm.task_id == task.id)))
    await session.delete(task)
    await session.commit()
    remove_from_disk(paths)


@router.post("/{task_id}/assignee-done", response_model=list[TaskAssigneeRead])
async def task_mark_done(payload: TaskAssigneeMarkDone | None = None,
                         access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.viewer)),
                         current_user: UsersOrm = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    task, _ = access
    task_id = task.id

    assignee = await TaskAssigneeRepository.get_assignee(session, task_id, current_user.id)
    if assignee is None:
        raise HTTPException(status_code=403, detail="This task is not assigned")

    if assignee.done_at is not None:
        raise HTTPException(status_code=409, detail="Task is already done")

    note = payload.done_note if payload else None
    await TaskAssigneeRepository.assignee_mark_done(session, assignee, note)

    assignees_list = await TaskAssigneeRepository.list_assignees(session, task_id)
    return [TaskAssigneeRead(user=PublicUser.model_validate(usr), done_at=t_a.done_at, done_note=t_a.done_note,
                             return_note=t_a.return_note) for t_a, usr in assignees_list]


@router.get("/{task_id}/assignees", response_model=list[TaskAssigneeRead])
async def get_task_assignee_list(access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.viewer)),
                      session: AsyncSession = Depends(get_session)):
    task, _ = access

    assignees_list = await TaskAssigneeRepository.list_assignees(session, task.id)
    return [TaskAssigneeRead(user=PublicUser.model_validate(usr), done_at=t_a.done_at)
            for t_a, usr in assignees_list]


@router.patch("/{task_id}/assignee-done", response_model=TaskAssigneeRead)
async def task_done_note_update(payload: TaskAssigneeMarkDone,
                                access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.viewer)),
                                current_user: UsersOrm = Depends(get_current_user),
                                session: AsyncSession = Depends(get_session)):
    task, _ = access
    task_id = task.id

    assignee = await TaskAssigneeRepository.get_assignee(session, task_id, current_user.id)
    if assignee is None:
        raise HTTPException(status_code=403, detail="This task is not assigned")

    if assignee.done_at is None:
        raise HTTPException(status_code=409, detail="Task is not marked as done")

    if "done_note" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="Nothing to update")

    res = TaskAssigneeRead(user=PublicUser.model_validate(current_user),
                           done_at=assignee.done_at,
                           done_note=payload.done_note,
                           return_note=assignee.return_note)

    await TaskAssigneeRepository.change_assignee_note(session, assignee, payload.done_note)
    return res


@router.delete("/{task_id}/assignee-done", status_code=204)
async def task_unmark_done(access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.viewer)),
                           current_user: UsersOrm = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    task, _ = access
    task_id = task.id

    assignee = await TaskAssigneeRepository.get_assignee(session, task_id, current_user.id)
    if assignee is None:
        raise HTTPException(status_code=403, detail="This task is not assigned")

    await TaskAssigneeRepository.unmark_assign(session, assignee)


@router.post("/{task_id}/assignees", response_model=list[TaskAssigneeRead])
async def exist_task_assign(payload: TaskAssigneesAdd,
                            access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.editor)),
                            current_user: UsersOrm = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session)):
    task, _ = access
    task_id = task.id

    target_pub_ids = {u.public_id for u in payload.assignees}
    contact_ids = target_pub_ids.copy()
    if current_user.public_id in contact_ids:
        contact_ids.remove(current_user.public_id)

    contact_check = await ContactsRepository.get_contacts_by_public_ids(session, current_user.id, list(contact_ids))

    if len(contact_ids) != len(contact_check):
        raise HTTPException(status_code=409, detail="Some of users are not in contacts")

    contacts_to_add = [usr.id for usr in contact_check]
    if current_user.public_id in target_pub_ids:
        contacts_to_add.append(current_user.id)

    await TaskAssigneeRepository.add_many_assignees(session, task_id, contacts_to_add, current_user.id)

    assignee_list = await TaskAssigneeRepository.list_assignees(session, task_id)
    return [TaskAssigneeRead(user=PublicUser.model_validate(usr), done_at=t_a.done_at) for t_a, usr in assignee_list]


@router.delete("/{task_id}/assignees/{public_id}", status_code=204)
async def task_unassign(public_id: str,
                        access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.editor)),
                        current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    task, role = access

    target_usr = await UsersRepository.get_by_public_id(session, public_id)
    if target_usr is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    assign = await TaskAssigneeRepository.get_assignee(session, task.id, target_usr.id)
    if assign is None:
        raise HTTPException(status_code=404, detail="Assign not found")

    if role != ProjectRole.owner and current_user.id != assign.assigned_by_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await TaskAssigneeRepository.assign_delete(session, assign.task_id, assign.user_id)


@router.post("/{task_id}/assignees/{public_id}/reject", response_model=list[TaskAssigneeRead])
async def task_assignee_reject(public_id: str,
                               payload: TaskAssigneeReject | None = None,
                               access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.editor)),
                               current_user: UsersOrm = Depends(get_current_user),
                               session: AsyncSession = Depends(get_session)):
    task, role = access
    task_id = task.id

    target_usr = await UsersRepository.get_by_public_id(session, public_id)

    if target_usr is None:
        raise HTTPException(status_code=404, detail="Assignee not found")

    assign = await TaskAssigneeRepository.get_assignee(session, task_id, target_usr.id)
    if assign is None:
        raise HTTPException(status_code=404, detail="Assignee not found")

    if role != ProjectRole.owner and current_user.id != assign.assigned_by_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    note = payload.return_note if payload else None

    await TaskAssigneeRepository.unmark_assign(session, assign, note)

    assignees = await TaskAssigneeRepository.list_assignees(session, task_id)

    return [TaskAssigneeRead(user=PublicUser.model_validate(usr),done_at=t_a.done_at,
                             done_note=t_a.done_note, return_note=t_a.return_note) for t_a, usr in assignees]


@router.patch("/{task_id}/assignees/{public_id}/reject", response_model=TaskAssigneeRead)
async def task_reject_note_update(public_id: str,
                                  payload: TaskAssigneeReject,
                                  access: tuple[TasksOrm, ProjectRole] = Depends(task_access(ProjectRole.editor)),
                                  current_user: UsersOrm = Depends(get_current_user),
                                  session: AsyncSession = Depends(get_session)):
    task, role = access
    task_id = task.id

    target_usr = await UsersRepository.get_by_public_id(session, public_id)

    if target_usr is None:
        raise HTTPException(status_code=404, detail="Assignee not found")

    assignee = await TaskAssigneeRepository.get_assignee(session, task_id, target_usr.id)
    if assignee is None:
        raise HTTPException(status_code=404, detail="Assignee not found")

    if role != ProjectRole.owner and current_user.id != assignee.assigned_by_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if "return_note" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="Nothing to update")

    res = TaskAssigneeRead(user=PublicUser.model_validate(target_usr),
                           done_at=assignee.done_at,
                           done_note=assignee.done_note,
                           return_note=payload.return_note)

    await TaskAssigneeRepository.change_reject_note(session, assignee, payload.return_note)
    return res