from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_current_user, require_project_role, require_item_role, Pagination
from src.models import UsersOrm, ProjectRole
from src.queries.orm import FoldersRepository
from src.schemas import FolderRead, FolderCreate, FolderUpdate

router = APIRouter(prefix="/folders", tags=["folders"])

@router.post("", response_model=FolderRead)
async def create_folder(payload: FolderCreate,
                        current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session),
                        ):
    if payload.project_id is not None:
        await require_project_role(session, payload.project_id, current_user.id, ProjectRole.editor)
    if payload.parent_folder_id is not None:
        parent = await FoldersRepository.get(session, payload.parent_folder_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        await require_item_role(session, parent, current_user, ProjectRole.editor)
        if parent.project_id != payload.project_id:
            raise HTTPException(status_code=400, detail="Subfolder must belong to the same project as its parent folder")

    return await FoldersRepository.create(session, owner_id=current_user.id, name=payload.name,
                                          parent_folder_id=payload.parent_folder_id, project_id=payload.project_id)


@router.get("", response_model=list[FolderRead])
async def list_folders(response: Response, page: Pagination = Depends(), project_id: int | None = None,
                       parent_folder_id: int | None = None,
                       current_user: UsersOrm = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)
                       ):
    items, total = await FoldersRepository.list_visible(
        session, current_user.id, parent_folder_id, project_id, page.limit, page.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.patch("/{folder_id}", response_model=FolderRead)
async def update_folder(folder_id: int, payload: FolderUpdate,
                        current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    folder = await FoldersRepository.get(session, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_item_role(session, folder, current_user, ProjectRole.editor)

    updates = payload.model_dump(exclude_unset=True)

    new_parent = updates.get("parent_folder_id")
    if new_parent is not None:
        parent = await FoldersRepository.get(session, new_parent)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        await require_item_role(session, parent, current_user, ProjectRole.editor)
        if parent.project_id != folder.project_id:
            raise HTTPException(status_code=400, detail="Parent folder must be in the same project")
        if await FoldersRepository.would_create_cycle(session, folder_id, new_parent):
            raise HTTPException(status_code=400, detail="Folder cannot be moved into itself or its descendant")

    return await FoldersRepository.update(session, folder, updates)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    folder = await FoldersRepository.get(session, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_item_role(session, folder, current_user, ProjectRole.editor)

    await session.delete(folder)
    await session.commit()
