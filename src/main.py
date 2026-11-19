from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.routers.router import router

app = FastAPI()
app.include_router(router)

static_dir = Path(__file__).resolve().parent.parent / "static"
index_file = static_dir / "index.html"

if index_file.is_file():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def frontend():
        return FileResponse(index_file)