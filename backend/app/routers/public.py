from fastapi import APIRouter, Query

from backend.app.dependencies import AppSessions
from backend.app.repositories.public_activity_repository import PublicActivityRepository
from backend.app.schemas import PublicRecentListenAlbum, SplashResponse
from backend.app.services.public_activity_service import recent_listened_albums, splash_payload


router = APIRouter(prefix="/public", tags=["public"])


@router.get("/recent-listens", response_model=list[PublicRecentListenAlbum])
def get_recent_public_listens(
    session_factory: AppSessions,
    limit: int = Query(default=5, ge=1, le=10),
) -> list[dict]:
    with session_factory() as session:
        return recent_listened_albums(PublicActivityRepository(session), limit=limit)


@router.get("/splash", response_model=SplashResponse)
def get_public_splash(session_factory: AppSessions) -> dict:
    with session_factory() as session:
        return splash_payload(PublicActivityRepository(session))
