from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import project_access, get_current_user, require_project_role
from src.models import ProjectsOrm, ProjectRole, UsersOrm, ROLE_RANK
from src.queries.orm import ContactsRepository, ProjectMembersRepository, UsersRepository
from src.schemas import ProjectMemberRead, MembersAdd, PublicUser, MemberRoleUpdate

router = APIRouter(tags=["members"])

@router.post("/projects/{project_id}/members", response_model=list[ProjectMemberRead])
async def add_many_to_project(payload: MembersAdd,
                              project: ProjectsOrm = Depends(project_access(ProjectRole.editor)),
                              session: AsyncSession = Depends(get_session),
                              current_user: UsersOrm = Depends(get_current_user)):

    project_id = project.id     # save before commit. Look expire_on_commit session param
    wanted = {m.public_id: m.role for m in payload.members}

    if ProjectRole.owner in wanted.values():
        await require_project_role(session, project.id, current_user.id, ProjectRole.owner)

    found = await ContactsRepository.get_contacts_by_public_ids(session, current_user.id, list(wanted))
    if len(found) != len(wanted):
        raise HTTPException(status_code=409, detail="Some of users are not in contacts")

    found_ids = {c.id for c in found}

    current_members = await ProjectMembersRepository.list_members(session, project.id)
    if any(u.id in found_ids for _, u in current_members):
        raise HTTPException(status_code=409, detail="Some of users already in project")

    members = [(u.id, wanted[u.public_id]) for u in found]
    await ProjectMembersRepository.add_many(session, project.id, members)

    rows = await ProjectMembersRepository.list_members(session, project_id)
    return [ProjectMemberRead(user=PublicUser.model_validate(u), role=m.role) for m, u in rows]


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberRead])
async def get_project_members_list(project: ProjectsOrm = Depends(project_access(ProjectRole.viewer)),
                                   session: AsyncSession = Depends(get_session),):
    members = await ProjectMembersRepository.list_members(session, project.id)
    return [ProjectMemberRead(user=PublicUser.model_validate(u), role=m.role) for m, u in members]


@router.patch("/projects/{project_id}/members/{public_id}", response_model = ProjectMemberRead)
async def change_member_role(public_id: str,
                             payload: MemberRoleUpdate,
                             project: ProjectsOrm = Depends(project_access(ProjectRole.owner)),
                             session: AsyncSession = Depends(get_session),):
    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")

    member = await ProjectMembersRepository.get_member(session, project.id, target.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.role == ProjectRole.owner and payload.role != ProjectRole.owner:
        if await ProjectMembersRepository.count_owners(session, project.id) == 1:
            raise HTTPException(status_code=409, detail="There must be at least one owner")

    card = PublicUser.model_validate(target)    # before commit. Look expire_on_commit session param
    member = await ProjectMembersRepository.update(session, member, {"role": payload.role})
    return ProjectMemberRead(user=card, role=member.role)


@router.delete("/projects/{project_id}/members/me", status_code=204)
async def leave_project(project: ProjectsOrm = Depends(project_access(ProjectRole.viewer)),
                        session: AsyncSession = Depends(get_session),
                        current_user: UsersOrm = Depends(get_current_user)):
    member = await ProjectMembersRepository.get_member(session, project.id, current_user.id)

    if member.role == ProjectRole.owner:
        if await ProjectMembersRepository.count_owners(session, project.id) == 1:
            raise HTTPException(status_code=409, detail="There must be at least one owner")

    await ProjectMembersRepository.delete(session, member.id)


@router.delete("/projects/{project_id}/members/{public_id}", status_code=204)
async def delete_project_member(public_id: str,
                                project: ProjectsOrm = Depends(project_access(ProjectRole.viewer)),
                                session: AsyncSession = Depends(get_session),
                                current_user: UsersOrm = Depends(get_current_user)):
    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")

    member = await ProjectMembersRepository.get_member(session, project.id, target.id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.id != current_user.id:
        my_role = await ProjectMembersRepository.get_role(session, project.id, current_user.id)
        if my_role != ProjectRole.owner and ROLE_RANK[my_role] <= ROLE_RANK[member.role]:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    if member.role == ProjectRole.owner:
        if await ProjectMembersRepository.count_owners(session, project.id) == 1:
            raise HTTPException(status_code=409, detail="There must be at least one owner")

    await ProjectMembersRepository.delete(session, member.id)