from fastapi import APIRouter

from backend.app.dependencies import AppSessions
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import AlbumState

router = APIRouter(tags=["albums"])


@router.get("/album-state", response_model=AlbumState)
def get_album_state(session_factory: AppSessions) -> AlbumState:
    with session_factory() as session:
        repository = SqliteStateRepository(session)
        return AlbumState.model_validate(repository.load_album_state())
