from fastapi import FastAPI

from backend.app.config import get_settings
from backend.app.routers import album_state, health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(album_state.router, prefix=settings.api_prefix)

    return app


app = create_app()
