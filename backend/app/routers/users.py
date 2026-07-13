from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy.orm import sessionmaker

import metadata_refresh_service
from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.manual_album_service import create_manual_album
from backend.app.schemas import (
    AlbumListenCreate,
    AlbumListenDelete,
    AlbumMergeRequest,
    AlbumMetadataUpdate,
    AlbumRefreshRequest,
    AlbumState,
    CompletedAlbum,
    ManualAlbumCreate,
    UserAlbumFeedbackUpdate,
    User,
    UserCreate,
    ProfileCreateResponse,
    UserAlbumTagsUpdate,
)
from backend.app.services import auth_service

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


def _require_owner(session, user_slug: str, authorization: str | None):
    return auth_service.require_profile_owner(
        session,
        user_slug=user_slug,
        authorization=authorization,
    )


@router.get("", response_model=list[User])
def list_users() -> list:
    session_factory = _session_factory()
    with session_factory() as session:
        repository = UserRepository(session)
        repository.ensure_default_user()
        session.commit()
        return [_user_payload(user) for user in repository.list_users()]


@router.post("", response_model=ProfileCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(request: UserCreate) -> object:
    session_factory = _session_factory()
    with session_factory() as session:
        repository = UserRepository(session)
        try:
            account = auth_service.create_account(
                session,
                email=request.email,
                password=request.password,
            )
            user = repository.create_user(
                slug=request.slug,
                display_name=request.display_name,
                owner_account_id=account.id,
                commit=False,
            )
            token = auth_service.create_session(session, account=account)
            session.commit()
            return ProfileCreateResponse(session_token=token, **_user_payload(user))
        except ValueError as exc:
            session.rollback()
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


@router.get("/{user_slug}/export", response_model=AlbumState)
def export_user_album_state(
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> AlbumState:
    """Return an owner-only portable snapshot of a profile's album history."""
    session_factory = _session_factory()
    with session_factory() as session:
        _require_owner(session, user_slug, authorization)
        repository = SqliteStateRepository(session, user_slug=user_slug)
        return AlbumState.model_validate(repository.load_album_state())


@router.post(
    "/{user_slug}/albums",
    response_model=CompletedAlbum,
    status_code=status.HTTP_201_CREATED,
)
def create_user_album(
    user_slug: str,
    request: ManualAlbumCreate,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
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
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.add_album_listen(album_id, request.listened_at)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{user_slug}/albums/{album_id}/listens", response_model=CompletedAlbum)
def delete_user_album_listen(
    user_slug: str,
    album_id: int,
    request: AlbumListenDelete,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.delete_album_listen(album_id, request.listened_at)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/{user_slug}/albums/{album_id}/your-tags", response_model=CompletedAlbum)
def update_user_album_tags(
    user_slug: str,
    album_id: int,
    request: UserAlbumTagsUpdate,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
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
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.update_user_album_feedback(
                album_id,
                rating=request.rating,
                notes=request.notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/refresh-metadata", response_model=CompletedAlbum)
def refresh_user_album_metadata(
    user_slug: str,
    album_id: int,
    request: AlbumRefreshRequest | None = None,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            existing = repository.get_completed_album_record_by_id(album_id)
            refreshed = metadata_refresh_service.refresh_album_record(
                existing,
                spotify_url=request.spotify_url if request else None,
            )
            refreshed.pop("_refresh_warnings", None)
            return repository.replace_completed_album_metadata_by_id_or_merge_duplicate(
                album_id,
                refreshed,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.patch("/{user_slug}/albums/{album_id}", response_model=CompletedAlbum)
def update_user_album(
    user_slug: str,
    album_id: int,
    request: AlbumMetadataUpdate,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.update_completed_album_fields(
                album_id,
                request.model_dump(exclude_unset=True),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/merge", response_model=CompletedAlbum)
def merge_user_album(
    user_slug: str,
    album_id: int,
    request: AlbumMergeRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return repository.merge_completed_album_listens(album_id, request.target_album_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/{user_slug}/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_album(
    user_slug: str,
    album_id: int,
    authorization: str | None = Header(default=None),
) -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            _require_owner(session, user_slug, authorization)
            SqliteStateRepository(session, user_slug=user_slug).delete_completed_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
