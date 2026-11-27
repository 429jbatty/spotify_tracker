from fastapi import APIRouter

from backend.app.dependencies import AppSession
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.schemas import AlbumState

router = APIRouter(tags=["albums"])


@router.get("/album-state", response_model=AlbumState)
def get_album_state(session: AppSession) -> AlbumState:
    user = UserRepository(session).ensure_default_user()
    return AlbumState.model_validate(AlbumStateRepository(session, user).load())
