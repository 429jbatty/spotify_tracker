from fastapi import APIRouter, Query
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.schemas import PublicRecentListenAlbum, SplashResponse
from backend.app.services.public_activity_service import (
    recent_listened_albums,
    splash_payload,
)


router = APIRouter(prefix="/public", tags=["public"])


def _session_factory():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@router.get("/recent-listens", response_model=list[PublicRecentListenAlbum])
def get_recent_public_listens(
    limit: int = Query(default=5, ge=1, le=10),
) -> list[dict]:
    session_factory = _session_factory()
    with session_factory() as session:
        return recent_listened_albums(session, limit=limit)


@router.get("/splash", response_model=SplashResponse)
def get_public_splash() -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        return splash_payload(session)
