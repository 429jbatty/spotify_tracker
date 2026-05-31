from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.routers import album_state, albums, health, imports, spotify
from backend.app.routers import users


def create_app() -> FastAPI:
    settings = get_settings()
    create_schema(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        imports.resume_interrupted_imports()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(album_state.router, prefix=settings.api_prefix)
    app.include_router(albums.router, prefix=settings.api_prefix)
    app.include_router(imports.router, prefix=settings.api_prefix)
    app.include_router(users.router, prefix=settings.api_prefix)
    app.include_router(spotify.router, prefix=settings.api_prefix)

    artwork_dir = Path(settings.media_dir) / "artwork"
    artwork_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/artwork",
        StaticFiles(directory=str(artwork_dir)),
        name="artwork",
    )

    return app


app = create_app()
