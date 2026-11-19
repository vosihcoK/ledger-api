from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_current_user, require_item_role, Pagination, require_project_role
from src.models import UsersOrm, ProjectRole
from src.queries.orm import TasksRepository, FoldersRepository, NotesRepository
from src.schemas import NoteRead, NoteUpdate, NoteCreate

router = APIRouter(prefix="/notes", tags=["notes"])

@router.post("", response_model=NoteRead)
async def create_note(payload: NoteCreate,
                      current_user: UsersOrm = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session),
                      ):
    # proj
    if payload.project_id is not None:
        await require_project_role(session, payload.project_id, current_user.id, ProjectRole.editor)
    # task
    if payload.task_id is not None:
        task = await TasksRepository.get(session, payload.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await require_item_role(session, task, current_user, ProjectRole.editor)
        if task.project_id != payload.project_id:
            raise HTTPException(status_code=400, detail="Note must belong to the same project as its task")
    # folder
    if payload.folder_id is not None:
        folder = await FoldersRepository.get(session, payload.folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found")
        await require_item_role(session, folder, current_user, ProjectRole.editor)
        if payload.project_id != folder.project_id:
            raise HTTPException(status_code=400, detail="Folder must belong to the same project as the note")

    return await NotesRepository.create(session, owner_id=current_user.id, title=payload.title, content=payload.content,
                                        folder_id=payload.folder_id, project_id=payload.project_id, task_id=payload.task_id)


@router.get("", response_model=list[NoteRead])
async def list_notes(response: Response, page: Pagination = Depends(),
                     folder_id: int | None = None, project_id: int | None = None, task_id: int | None = None,
                     current_user: UsersOrm = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)
                     ):
    items, total = await NotesRepository.list_visible(
        session, current_user.id, folder_id, project_id, task_id, page.limit, page.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
                      note_id: int,
                      payload: NoteUpdate,
                      current_user: UsersOrm = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session),
                      ):
    note = await NotesRepository.get(session, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    await require_item_role(session, note, current_user, ProjectRole.editor)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("folder_id") is not None:
        folder = await FoldersRepository.get(session, updates["folder_id"])
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found")
        await require_item_role(session, folder, current_user, ProjectRole.editor)
        if folder.project_id != note.project_id:
            raise HTTPException(status_code=400, detail="Folder must belong to the same project as the note")
    return await NotesRepository.update(session, note, updates)


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int,
                      current_user: UsersOrm = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    note = await NotesRepository.get(session, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    await require_item_role(session, note, current_user, ProjectRole.editor)
    await session.delete(note)
    await session.commit()