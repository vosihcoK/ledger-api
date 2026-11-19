from fastapi import APIRouter
from . import contacts, files, folders, members, notes, plans, projects, tasks, user, calendar

router = APIRouter()

for r in (contacts.router, files.router, folders.router, members.router, notes.router, plans.router,
               projects.router, tasks.router, user.router, calendar.router):
    router.include_router(r)
