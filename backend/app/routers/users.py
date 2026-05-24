from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.manual_album_service import create_manual_album
from backend.app.schemas import (
    AlbumListenCreate,
    AlbumListenDelete,
    AlbumState,
    CompletedAlbum,
    ManualAlbumCreate,
    UserAlbumFeedbackUpdate,
    User,
    UserCreate,
    UserAlbumTagsUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


def _session_factory():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "slug": user.slug,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


@router.get("", response_model=list[User])
def list_users() -> list:
    session_factory = _session_factory()
    with session_factory() as session:
        repository = UserRepository(session)
        repository.ensure_default_user()
        session.commit()
        return [_user_payload(user) for user in repository.list_users()]


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(request: UserCreate) -> object:
    session_factory = _session_factory()
    with session_factory() as session:
        repository = UserRepository(session)
        try:
            user = repository.create_user(
                slug=request.slug,
                display_name=request.display_name,
            )
            return _user_payload(user)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/{user_slug}/album-state", response_model=AlbumState)
def get_user_album_state(user_slug: str) -> AlbumState:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return AlbumState.model_validate(repository.load_album_state())
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{user_slug}/albums",
    response_model=CompletedAlbum,
    status_code=status.HTTP_201_CREATED,
)
def create_user_album(user_slug: str, request: ManualAlbumCreate) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return create_manual_album(repository, request)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/listens", response_model=CompletedAlbum)
def add_user_album_listen(
    user_slug: str,
    album_id: int,
    request: AlbumListenCreate,
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.add_album_listen(album_id, request.listened_at)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{user_slug}/albums/{album_id}/listens", response_model=CompletedAlbum)
def delete_user_album_listen(
    user_slug: str,
    album_id: int,
    request: AlbumListenDelete,
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.delete_album_listen(album_id, request.listened_at)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/{user_slug}/albums/{album_id}/your-tags", response_model=CompletedAlbum)
def update_user_album_tags(
    user_slug: str,
    album_id: int,
    request: UserAlbumTagsUpdate,
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.update_user_album_tags(album_id, request.your_tags)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put("/{user_slug}/albums/{album_id}/your-feedback", response_model=CompletedAlbum)
def update_user_album_feedback(
    user_slug: str,
    album_id: int,
    request: UserAlbumFeedbackUpdate,
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.update_user_album_feedback(
                album_id,
                rating=request.rating,
                notes=request.notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
