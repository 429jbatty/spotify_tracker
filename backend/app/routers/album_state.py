from fastapi import APIRouter, HTTPException

from backend.app.dependencies import AppSession
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.schemas import AlbumState

router = APIRouter(tags=["albums"])


@router.get("/album-state", response_model=AlbumState, deprecated=True)
def get_album_state(session: AppSession, user_slug: str) -> AlbumState:
    user = UserRepository(session).get_user_by_slug(user_slug)
    if user is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return AlbumState.model_validate(AlbumStateRepository(session, user).load())
