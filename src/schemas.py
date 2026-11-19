import zoneinfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from typing import Optional, ClassVar
from datetime import datetime, date
from src.models import TaskStatus, PlanStatus, ProjectRole

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"

class PatchModel(BaseModel):
    """BASE for PATCH schemes: explicit null is prohibited for NOT NULL columns."""
    non_nullable: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for name in self.non_nullable:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #   owner_id: int
    name: str
    description: Optional[str]
    color: Optional[str]
    due_date: Optional[datetime]
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

class ProjectListItem(ProjectRead):
    my_role: ProjectRole

class ProjectUpdate(PatchModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("name", "is_archived")

    name: Optional[str]              = None
    description: Optional[str]       = None
    color: Optional[str]             = None
    due_date: Optional[datetime]     = None
    is_archived: Optional[bool]      = None
    completed_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=64)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long (max 72 bytes)")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #   id: int
    email: str
    public_id: str
    display_name: Optional[str]
    status: Optional[str]
    bio: Optional[str]
    avatar_color: Optional[str]
    timezone: Optional[str]
    week_start: int

    is_active: bool
    created_at: datetime
    # password_hash     should never leave in response to a client


class UserUpdate(PatchModel):
    non_nullable: ClassVar = {"week_start"}
    display_name: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=280)
    avatar_color: str | None = Field(default=None, pattern=HEX_COLOR)
    timezone: str | None = None
    week_start: int | None = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None and v not in zoneinfo.available_timezones():
            raise ValueError("Unknown time zone")
        return v

class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #id: int
    public_id: str
    display_name: str | None = None
    avatar_color: str | None = None
    status: str | None = None

class ContactRequestRead(BaseModel):
    id: int
    created_at: datetime
    from_user: PublicUser

class ContactRead(BaseModel):
    user: PublicUser
    alias: str | None = None

class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str | None = Field(default=None, max_length=20)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long (max 72 bytes)")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
#    owner_id: int
    project_id: Optional[int]
    stage_id: Optional[int]
    parent_task_id: Optional[int]
    title: str
    description: Optional[str]
    status: str
    priority: int
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class PlanCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None

class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    #   owner_id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]    # SHOULD BE OPTIONAL!
    status: str
    converted_to_project_id: Optional[int]
    converted_to_task_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class ProgressRead(BaseModel):
    total_tasks: int
    completed_tasks: int
    progress_pct: float


class CalendarItemRead(BaseModel):
    item_type: str
    id: int
    title: str
    due_date: datetime


class StageCreate(BaseModel):
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    order_index: int = 0

class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str]
    order_index: int
    due_date: Optional[date]
    created_at: datetime
    updated_at: datetime

class StageUpdate(PatchModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("name", "order_index")

    name:        Optional[str] = None
    description: Optional[str] = None
    due_date:    Optional[datetime] = None
    order_index: Optional[int] = None

class TaskUpdate(PatchModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("title", "status", "priority", "order_index")

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[int] = Field(None, ge=0, le=3)
    due_date: Optional[datetime] = None
    stage_id: Optional[int] = None
    order_index: Optional[int] = None

class PlanUpdate(BaseModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("title", "status")

    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[PlanStatus] = None

    @field_validator("status")
    @classmethod
    def status_not_converted(cls, v):
        if v == PlanStatus.converted:
            raise ValueError("Use convert-to-task / convert-to-project endpoints")
        return v


class FolderCreate(BaseModel):
    name: str
    parent_folder_id: Optional[int] = None
    project_id: Optional[int] = None

class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #   owner_id: int
    parent_folder_id: Optional[int]
    project_id: Optional[int]
    name: str
    order_index: int
    created_at: datetime
    updated_at: datetime

class FolderUpdate(PatchModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("name",)

    name:             Optional[str] = None
    parent_folder_id: Optional[int] = None


class NoteCreate(BaseModel):
    title: Optional[str] = None
    content: str = ""
    folder_id: Optional[int] = None
    project_id: Optional[int] = None
    task_id: Optional[int] = None

class NoteUpdate(BaseModel):
    non_nullable: ClassVar[tuple[str, ...]] = ("content",)

    title: Optional[str] = None
    content: Optional[str] = None
    folder_id: Optional[int] = None

class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    #   owner_id: int
    folder_id: Optional[int]
    project_id: Optional[int]
    task_id: Optional[int]
    title: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    #   owner_id: int
    project_id: Optional[int]
    task_id: Optional[int]
    filename: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    created_at: datetime
    # storage_path internal path on the server disk


class ContactRequestCreate(BaseModel):
    public_id: str


class ContactRequestResult(BaseModel):
    status: str = "sent"

class ProjectMemberRead(BaseModel):
    user: PublicUser
    role: ProjectRole

class MemberAdd(BaseModel):
    public_id: str
    role: ProjectRole

class MembersAdd(BaseModel):
    members: list[MemberAdd]

class MemberRoleUpdate(BaseModel):
    role: ProjectRole


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    due_date: Optional[datetime] = None
    members: list[MemberAdd] = Field(default_factory=list)


class TaskAssigneeRead(BaseModel):
    user: PublicUser
    done_at: datetime | None = None
    done_note:    str | None = None
    return_note:  str | None = None

class TaskAssigneeAdd(BaseModel):
    public_id: str

class TaskAssigneesAdd(BaseModel):
    assignees: list[TaskAssigneeAdd] = Field(min_length=1)

class TaskCreate(BaseModel):
    title: str
    description: Optional[str]    = None
    project_id: Optional[int]     = None
    stage_id: Optional[int]       = None
    parent_task_id: Optional[int] = None
    due_date: Optional[datetime]  = None
    priority: int = 0
    assignees: list[TaskAssigneeAdd] = Field(default_factory=list)

class TaskAssigneeReject(BaseModel):
    return_note: str | None = Field(default=None, max_length=300)

    @field_validator("return_note")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v


class TaskAssigneeMarkDone(BaseModel):
    done_note: str | None = Field(default=None, max_length=300)

    @field_validator("done_note")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v


