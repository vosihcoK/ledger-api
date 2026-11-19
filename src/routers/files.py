import os
import uuid

from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response, UploadFile, File, Form
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import FileResponse

from src.dependencies import get_current_user, require_project_role, require_item_role, Pagination
from src.models import UsersOrm, ProjectRole
from src.queries.orm import TasksRepository, FilesRepository
from src.schemas import FileRead

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/files", tags=["files"])

@router.post("", response_model=FileRead)
async def upload_file(
    file: UploadFile = File(...),
    project_id: int | None = Form(None),
    task_id: int | None = Form(None),
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if project_id is not None:
        await require_project_role(session, project_id, current_user.id, ProjectRole.editor)
    if task_id is not None:
        task = await TasksRepository.get(session, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.project_id != project_id:
            raise HTTPException(status_code=400, detail="File must belong to the same project as its task")
        await require_item_role(session, task, current_user, ProjectRole.editor)

    ext = os.path.splitext(file.filename)[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_path = os.path.join(UPLOAD_DIR, stored_name)

    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 25 MB)")

    with open(storage_path, "wb") as f:
        f.write(contents)

    return await FilesRepository.create(
        session, owner_id=current_user.id, filename=file.filename, storage_path=storage_path,
        mime_type=file.content_type, size_bytes=len(contents),
        project_id=project_id, task_id=task_id,
    )


@router.get("", response_model=list[FileRead])
async def list_files(
    response: Response, page: Pagination = Depends(),
    project_id: int | None = None,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items, total = await FilesRepository.list_visible(session, current_user.id, project_id, page.limit, page.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    file_record = await FilesRepository.get(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found")
    await require_item_role(session, file_record, current_user, ProjectRole.viewer)
    return FileResponse(file_record.storage_path, filename=file_record.filename, media_type=file_record.mime_type)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    file_record = await FilesRepository.get(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found")
    await require_item_role(session, file_record, current_user, ProjectRole.editor)

    path = file_record.storage_path
    await session.delete(file_record)
    await session.commit()
    if os.path.exists(path):
        os.remove(path)