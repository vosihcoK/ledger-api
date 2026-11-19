import datetime
from typing import Optional, Annotated, Any

from sqlalchemy import TypeDecorator, DateTime, String, ForeignKey, text, \
    CheckConstraint, Enum as SqlEnum, Dialect, Text, BigInteger, SmallInteger, Enum, UniqueConstraint, Index, \
    PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.type_api import _T

from src.database import Base, str_256, str_100, str_7
import enum

from utils.gen_pub_id import ID_LEN


int_pk = Annotated[int, mapped_column(primary_key=True)]
nullable_str_100 = Annotated[str_100, mapped_column(nullable=True)]
boolean_def_true = Annotated[bool, mapped_column(default=True)]
boolean_def_false = Annotated[bool, mapped_column(default=False)]
created_at = Annotated[datetime.datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"))]
updated_at = Annotated[datetime.datetime, mapped_column(
        server_default=text("TIMEZONE('utc', now())"),
        onupdate=text("TIMEZONE('utc', now())"))]

# another custom type for UTC convert from user input
class UTCDateTime(TypeDecorator):
    impl = DateTime

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    def process_result_value(
        self, value: Optional[Any], dialect: Dialect
    ) -> Optional[_T]:
        if value is not None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value

datetime_UTC = Annotated[datetime.datetime, mapped_column(UTCDateTime)]


class ContactsRequestsStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepting"
    declined = "declined"
    cancelled = "cancelled"


class UsersOrm(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int_pk]
    public_id: Mapped[str] = mapped_column(String(ID_LEN), unique=True)
    status: Mapped[nullable_str_100]
    bio: Mapped[str | None] = mapped_column(String(280))
    avatar_color: Mapped[str | None] = mapped_column(String(7)) # "#c4566b"
    timezone: Mapped[str | None] = mapped_column(String(64))    # "Eu/Mo"
    week_start: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")

    email: Mapped[str_256]
    password_hash: Mapped[str_256]
    display_name: Mapped[nullable_str_100]
    is_active: Mapped[boolean_def_true]
    email_verified_at: Mapped[Optional[datetime.datetime]]
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]

class ContactsRequestsOrm(Base):
    __tablename__ = "contacts_requests"

    id: Mapped[int_pk]
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[ContactsRequestsStatus] = mapped_column(default=ContactsRequestsStatus.pending)
    created_at: Mapped[created_at]
    responded_at: Mapped[Optional[datetime_UTC]]

    # be sure the pending status request can be received once. IntegrityError would raise if same pair exists in tables index. After refusing it can be also send second time. It can be legally bilateral one time.
    __table_args__ = (
        Index("uq_constraint_requests_pending", "from_id", "to_id",
              unique=True, postgresql_where=text("status = 'pending'")),
    )

# address book, by line for each direction
class ContactsOrm(Base):
    __tablename__ = "contacts"

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    alias: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[created_at]

    # primary_key=True argument in mapped_column is same thing
    __table_args__ = (
        PrimaryKeyConstraint("owner_id", "contact_id"),
    )


class ProjectsOrm(Base):
    __tablename__ = "projects"
    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str_256]
    description: Mapped[Optional[str]]
    color: Mapped[Optional[str_7]]
    due_date: Mapped[Optional[datetime_UTC]]
    is_archived: Mapped[boolean_def_false]
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]
    completed_at: Mapped[Optional[datetime_UTC]]

# user workpsace functionality
class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"

class PlanStatus(str, enum.Enum):
    open = "open"
    done = "done"
    converted = "converted"
    archived = "archived"


class TasksOrm(Base):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint(
        "stage_id IS NULL OR project_id IS NOT NULL", name="chk_stage_requires_project"),)

    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    stage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"))
    parent_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str_256]
    description: Mapped[Optional[str]]
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus, name="task_status"), default=TaskStatus.todo)
    priority: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[Optional[datetime_UTC]]
    completed_at: Mapped[Optional[datetime_UTC]]
    order_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]


class StagesOrm(Base):
    __tablename__ = "stages"
    id: Mapped[int_pk]
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str_256]
    description: Mapped[Optional[str]]
    order_index: Mapped[int]
    due_date: Mapped[Optional[datetime_UTC]]
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]


class PlansOrm(Base):
    __tablename__ = "plans"
    __table_args__ = (CheckConstraint(
        "converted_to_project_id IS NULL OR converted_to_task_id IS NULL",
        name="chk_plan_single_conversation",
        ),
    )

    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str_256]
    description: Mapped[Optional[str]]
    due_date: Mapped[Optional[datetime_UTC]]
    status: Mapped[PlanStatus] = mapped_column(SqlEnum(PlanStatus, name="plan_status"), default=PlanStatus.open)
    converted_to_project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    converted_to_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]



class FoldersOrm(Base):
    __tablename__ = "folders"

    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_folder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str_256]
    order_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]

class NotesOrm(Base):
    __tablename__ = "notes"

    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    folder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folders.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[Optional[str]] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]


class FilesOrm(Base):
    __tablename__ = "files"

    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[created_at]


class RefreshTokensOrm(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str_256]
    expires_at: Mapped[datetime_UTC]
    revoked_at: Mapped[Optional[datetime_UTC]]
    created_at: Mapped[created_at]


class ProjectRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"

ROLE_RANK = {ProjectRole.viewer: 1, ProjectRole.editor: 2, ProjectRole.owner: 3}


class ProjectMembersOrm(Base):
    __tablename__ = "proj_members"

    id: Mapped[int_pk]
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True) # frequent DB requests for inclusion

    # native_enum makes the column a regular line (str). It is inconvenient to change native enum types of Postgres by migrations.
    role: Mapped[ProjectRole] = mapped_column(Enum(ProjectRole, native_enum=False, length=16))
    created_at: Mapped[created_at]

    # connection member-project should be included once
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)


class TaskAssigneesOrm(Base):
    __tablename__ = "task_assignees"

    id: Mapped[int_pk]
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    assigned_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_at: Mapped[created_at]
    done_at: Mapped[Optional[datetime_UTC]]

    done_note: Mapped[Optional[str]] = mapped_column(String(300))
    return_note: Mapped[Optional[str]] = mapped_column(String(300))

    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_member"),)




