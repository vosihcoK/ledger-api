from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import Pagination, get_current_user
from src.models import UsersOrm, PlanStatus
from src.queries.orm import PlansRepository
from src.schemas import PlanRead, TaskRead, PlanCreate, PlanUpdate, ProjectRead

router = APIRouter(prefix="/plans", tags=["plans"])

@router.get("", response_model=list[PlanRead])
async def list_plans(response: Response, page: Pagination = Depends(),
                     current_user: UsersOrm = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    items, total = await PlansRepository.list_by_owner(
        session, current_user.id, page.limit, page.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/{plan_id}/convert-to-task", response_model=TaskRead)
async def covert_plan_to_task(
        plan_id: int,
        current_user: UsersOrm = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    plan = await PlansRepository.get_owned(session, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status != PlanStatus.open:
        raise HTTPException(status_code=400, detail="Plan already converted or archived")
    return await PlansRepository.convert_to_task(session, plan)


@router.post("", response_model=PlanRead)
async def create_plan(payload: PlanCreate,
                      session: AsyncSession = Depends(get_session),
                      current_user: UsersOrm = Depends(get_current_user)
                      ):
    return await PlansRepository.create(session, owner_id=current_user.id, title=payload.title,
                                        description=payload.description, due_date=payload.due_date)


@router.patch("/{plan_id}", response_model=PlanRead)
async def update_plan(plan_id: int, payload: PlanUpdate, current_user: UsersOrm = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session),
                      ):
    plan = await PlansRepository.get_owned(session, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status == PlanStatus.converted:
        raise HTTPException(status_code=400, detail="Converted plan is read-only")
    return await PlansRepository.update(session, plan, payload.model_dump(exclude_unset=True))


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id, current_user: UsersOrm = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    plan = await PlansRepository.get_owned(session, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    await session.delete(plan)
    await session.commit()


@router.post("/{plan_id}/convert-to-project", response_model=ProjectRead)
async def convert_plan_to_project(
        plan_id: int,
        current_user: UsersOrm = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    plan = await PlansRepository.get_owned(session, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status != PlanStatus.open:
        raise HTTPException(status_code=404, detail="Plan already converted or archived")

    return await PlansRepository.convert_to_project(session, plan)