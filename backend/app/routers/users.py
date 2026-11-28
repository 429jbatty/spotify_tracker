from fastapi import APIRouter, Header, HTTPException, status

from backend.app.services import metadata_refresh_logging
from backend.app.dependencies import AppSession
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.services.manual_album_service import (
    add_manual_album_listen, create_manual_album, delete_manual_album, delete_manual_album_listen,
    update_manual_album_feedback, update_manual_album_tags,
)
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
def list_users(session: AppSession) -> list:
    return [_user_payload(user) for user in UserRepository(session).list_users()]


@router.post("", response_model=ProfileCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(session: AppSession, request: UserCreate, authorization: str | None = Header(default=None)) -> object:
    try:
        account = auth_service.require_account(session, authorization=authorization)
        user, token = auth_service.create_owned_profile(
            session, account=account, slug=request.slug, display_name=request.display_name,
        )
        return ProfileCreateResponse(session_token=token, **_user_payload(user))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc



@router.get("/{user_slug}/album-state", response_model=AlbumState)
def get_user_album_state(session: AppSession, user_slug: str) -> AlbumState:
    try:
        user = UserRepository(session).require_user_by_slug(user_slug)
        return AlbumState.model_validate(AlbumStateRepository(session, user).load())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{user_slug}/export", response_model=AlbumState)
def export_user_album_state(
    session: AppSession,
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> AlbumState:
    """Return an owner-only portable snapshot of a profile's album history."""
    user = _require_owner(session, user_slug, authorization)
    return AlbumState.model_validate(AlbumStateRepository(session, user).load())


@router.post(
    "/{user_slug}/albums",
    response_model=CompletedAlbum,
    status_code=status.HTTP_201_CREATED,
)
def create_user_album(
    session: AppSession,
    user_slug: str,
    request: ManualAlbumCreate,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return create_manual_album(repository, request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/listens", response_model=CompletedAlbum)
def add_user_album_listen(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: AlbumListenCreate,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return add_manual_album_listen(repository, album_id, request.listened_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{user_slug}/albums/{album_id}/listens", response_model=CompletedAlbum)
def delete_user_album_listen(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: AlbumListenDelete,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return delete_manual_album_listen(repository, album_id, request.listened_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/{user_slug}/albums/{album_id}/your-tags", response_model=CompletedAlbum)
def update_user_album_tags(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: UserAlbumTagsUpdate,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return update_manual_album_tags(repository, album_id, request.your_tags)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put("/{user_slug}/albums/{album_id}/your-feedback", response_model=CompletedAlbum)
def update_user_album_feedback(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: UserAlbumFeedbackUpdate,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return update_manual_album_feedback(
            repository,
            album_id,
            rating=request.rating,
            notes=request.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/refresh-metadata", response_model=CompletedAlbum)
def refresh_user_album_metadata(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: AlbumRefreshRequest | None = None,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        album = repository.require_member(album_id)
        return metadata_refresh_logging.refresh_album(
            repository, album, spotify_url=request.spotify_url if request else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.patch("/{user_slug}/albums/{album_id}", response_model=CompletedAlbum)
def update_user_album(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: AlbumMetadataUpdate,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return repository.patch_metadata(
            album_id,
            request.model_dump(exclude_unset=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{user_slug}/albums/{album_id}/merge", response_model=CompletedAlbum)
def merge_user_album(
    session: AppSession,
    user_slug: str,
    album_id: int,
    request: AlbumMergeRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    try:
        user = _require_owner(session, user_slug, authorization)
        repository = AlbumLibrary(session, user)
        return repository.merge(album_id, request.target_album_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/{user_slug}/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_album(
    session: AppSession,
    user_slug: str,
    album_id: int,
    authorization: str | None = Header(default=None),
) -> None:
    try:
        user = _require_owner(session, user_slug, authorization)
        delete_manual_album(AlbumLibrary(session, user), album_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
