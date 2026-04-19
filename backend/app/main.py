from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.app.config import get_settings
from backend.app.routers import album_state, albums, health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(album_state.router, prefix=settings.api_prefix)
    app.include_router(albums.router, prefix=settings.api_prefix)

    artwork_dir = Path(settings.media_dir) / "artwork"
    artwork_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/artwork",
        StaticFiles(directory=str(artwork_dir)),
        name="artwork",
    )

    return app


app = create_app()
