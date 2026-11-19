from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.dependencies import get_current_user, project_access, remove_from_disk, project_file_paths
from src.models import UsersOrm, ProjectsOrm, ProjectMembersOrm, ProjectRole
from src.queries.orm import ContactsRepository, ProjectMembersRepository, ProjectsRepository, TasksRepository, \
    StagesRepository
from src.schemas import ProjectRead, ProjectCreate, ProjectListItem, ProgressRead, StageUpdate, ProjectUpdate, \
    StageRead, StageCreate

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("", response_model=ProjectRead)
async def create_project(payload: ProjectCreate,
                         current_user: UsersOrm = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session),):

    wanted = {i.public_id: i.role for i in payload.members}

    if current_user.public_id in wanted:
        raise HTTPException(status_code=422, detail="Creator is always the member")

    contacts = []
    if wanted:
        contacts = await ContactsRepository.get_contacts_by_public_ids(session, current_user.id, list(wanted))
        if len(wanted) != len(contacts):
            raise HTTPException(status_code=409, detail="Some of users are not in contacts")

    project = ProjectsOrm(**payload.model_dump(exclude={"members"}), owner_id=current_user.id)
    session.add(project)
    await session.flush()       # insert sent, get project.id

    session.add(ProjectMembersOrm(project_id=project.id, user_id=current_user.id, role=ProjectRole.owner,))
    rows = [(u.id, wanted[u.public_id]) for u in contacts]
    await ProjectMembersRepository.add_many(session, project.id, rows, commit=False)

    await session.commit()      # proj member and owner by one
    await session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def read_project(project: ProjectsOrm = Depends(project_access(ProjectRole.viewer))):
    return project


@router.get("", response_model=list[ProjectListItem])
async def list_projects(current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    rows = await ProjectsRepository.list_by_user(session, current_user.id)
    return [
        ProjectListItem(**ProjectRead.model_validate(project).model_dump(), my_role=role)
        for project, role in rows
    ]


@router.get("/{project_id}/progress", response_model=ProgressRead)
async def get_project_progress(
        project: ProjectsOrm = Depends(project_access(ProjectRole.viewer)),
        session: AsyncSession = Depends(get_session),
):
    return await TasksRepository.get_progress(session, project.id)


@router.post("/{project_id}/stages", response_model=StageRead)
async def create_stage(
        payload: StageCreate,
        project: ProjectsOrm = Depends(project_access(ProjectRole.editor)),
        session: AsyncSession = Depends(get_session),
        ):
    return await StagesRepository.create(session=session, project_id=project.id, name=payload.name,
                                         description=payload.description, due_date=payload.due_date,
                                         order_index=payload.order_index)


@router.get("/{project_id}/stages", response_model=list[StageRead])
async def list_stages(
        project: ProjectsOrm = Depends(project_access(ProjectRole.viewer)),
        session: AsyncSession = Depends(get_session)
):
    return await StagesRepository.list_by_project(session, project_id=project.id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(payload: ProjectUpdate,
                         project: ProjectsOrm = Depends(project_access(ProjectRole.editor)),
                         session: AsyncSession = Depends(get_session)):
    return await ProjectsRepository.update(session, project, payload.model_dump(exclude_unset=True))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project: ProjectsOrm = Depends(project_access(ProjectRole.owner)),
                         session: AsyncSession = Depends(get_session)):
    paths = await project_file_paths(session, project.id)
    await session.delete(project)
    await session.commit()
    remove_from_disk(paths)


@router.patch("/{project_id}/stages/{stage_id}", response_model=StageRead)
async def update_stage(payload: StageUpdate, stage_id: int,
                       project: ProjectsOrm = Depends(project_access(ProjectRole.editor)),
                       session: AsyncSession = Depends(get_session),
                       ):
    stage = await StagesRepository.get_by_project(session=session, stage_id=stage_id, project_id=project.id)
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return await StagesRepository.update(session, stage, payload.model_dump(exclude_unset=True))


@router.delete("/{project_id}/stages/{stage_id}", status_code=204)
async def delete_stage(stage_id: int,
                       project: ProjectsOrm = Depends(project_access(ProjectRole.editor)),
                       session: AsyncSession = Depends(get_session)):
    stage = await StagesRepository.get_by_project(session, stage_id, project.id)
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    await session.delete(stage)
    await session.commit()