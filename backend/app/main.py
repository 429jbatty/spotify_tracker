from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.app.logging_config import configure_logging
from backend.app.request_logging import RequestLoggingMiddleware
from backend.app.config import get_settings
from backend.app.database.engine import get_engine, session_factory_for
from backend.app.database.schema import initialize_database
from backend.app.services.artwork_static_files import ArtworkStaticFiles
from backend.app.routers import (
    album_state,
    albums,
    auth,
    credit_intelligence,
    health,
    imports,
    public,
    spotify,
)
from backend.app.routers import users


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    engine = get_engine(settings.database_url)
    try:
        initialize_database(engine)
    except Exception:
        engine.dispose()
        raise
    session_factory = session_factory_for(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            imports.resume_interrupted_imports(session_factory)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.session_factory = session_factory
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(album_state.router, prefix=settings.api_prefix)
    app.include_router(albums.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(credit_intelligence.router, prefix=settings.api_prefix)
    app.include_router(imports.router, prefix=settings.api_prefix)
    app.include_router(public.router, prefix=settings.api_prefix)
    app.include_router(users.router, prefix=settings.api_prefix)
    app.include_router(spotify.router, prefix=settings.api_prefix)

    artwork_dir = Path(settings.media_dir) / "artwork"
    artwork_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/artwork",
        ArtworkStaticFiles(directory=str(artwork_dir)),
        name="artwork",
    )

    return app


app = create_app()
