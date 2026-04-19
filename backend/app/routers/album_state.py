from fastapi import APIRouter
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.json_state_repository import JsonStateRepository
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import AlbumState

router = APIRouter(tags=["albums"])


@router.get("/album-state", response_model=AlbumState)
def get_album_state() -> AlbumState:
    settings = get_settings()
    if settings.album_state_backend == "sqlite":
        engine = get_engine(settings.database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            repository = SqliteStateRepository(session)
            return AlbumState.model_validate(repository.load_album_state())

    repository = JsonStateRepository(settings.state_file)
    return AlbumState.model_validate(repository.load_album_state())
