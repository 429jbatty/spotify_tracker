from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.app.services import metadata_refresh_logging
from backend.app.dependencies import AppSessions
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import DEFAULT_USER_SLUG
from backend.app.services.manual_album_service import (
    add_manual_album_listen, create_manual_album, delete_manual_album, delete_manual_album_listen,
    update_manual_album_feedback, update_manual_album_tags,
)
from backend.app.services import auth_service
from backend.app.schemas import (
    AlbumListenCreate,
    AlbumListenDelete,
    AlbumMergeRequest,
    AlbumMetadataUpdate,
    AlbumRefreshRequest,
    CompletedAlbum,
    ManualAlbumCreate,
    UserAlbumFeedbackUpdate,
    UserAlbumTagsUpdate,
)


router = APIRouter(prefix="/albums", tags=["albums"])
DUPLICATE_KEY_PREFIX = "Album key already exists: "


def _default_album_repository(
    session_factory: AppSessions,
    authorization: str | None = Header(default=None),
) -> Iterator[SqliteStateRepository]:
    with session_factory() as session:
        auth_service.require_profile_owner(
            session,
            user_slug=DEFAULT_USER_SLUG,
            authorization=authorization,
        )
        yield SqliteStateRepository(session, user_slug=DEFAULT_USER_SLUG)


DefaultAlbumRepository = Annotated[SqliteStateRepository, Depends(_default_album_repository)]


def _duplicate_album_detail(repository: SqliteStateRepository, error: ValueError):
    message = str(error)
    if not message.startswith(DUPLICATE_KEY_PREFIX):
        return message

    album_key = message.removeprefix(DUPLICATE_KEY_PREFIX)
    try:
        target_album = repository.get_completed_album_record(album_key)
    except KeyError:
        return message

    return {
        "code": "duplicate_album_key",
        "message": message,
        "target_album": target_album,
    }


@router.post(
    "/{album_id}/refresh-metadata",
    response_model=CompletedAlbum,
)
def refresh_album_metadata(
    repository: DefaultAlbumRepository,
    album_id: int,
    request: AlbumRefreshRequest | None = None,
) -> dict:
    try:
        return metadata_refresh_logging.refresh_album(
            repository, album_id, spotify_url=request.spotify_url if request else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("", response_model=CompletedAlbum, status_code=status.HTTP_201_CREATED)
def create_album(repository: DefaultAlbumRepository, request: ManualAlbumCreate) -> dict:
    try:
        return create_manual_album(repository, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.patch("/{album_id}", response_model=CompletedAlbum)
def update_album(repository: DefaultAlbumRepository, album_id: int, request: AlbumMetadataUpdate) -> dict:
    fields = request.model_dump(exclude_unset=True)
    try:
        return repository.update_completed_album_fields(album_id, fields)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_duplicate_album_detail(repository, exc),
        )


@router.post("/{album_id}/listens", response_model=CompletedAlbum)
def add_album_listen(repository: DefaultAlbumRepository, album_id: int, request: AlbumListenCreate) -> dict:
    try:
        return add_manual_album_listen(repository, album_id, request.listened_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{album_id}/listens", response_model=CompletedAlbum)
def delete_album_listen(repository: DefaultAlbumRepository, album_id: int, request: AlbumListenDelete) -> dict:
    try:
        return delete_manual_album_listen(repository, album_id, request.listened_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{album_id}/merge", response_model=CompletedAlbum)
def merge_album(repository: DefaultAlbumRepository, album_id: int, request: AlbumMergeRequest) -> dict:
    try:
        return repository.merge_completed_album_listens(
            album_id,
            request.target_album_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(repository: DefaultAlbumRepository, album_id: int) -> None:
    try:
        delete_manual_album(repository, album_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put("/{album_id}/your-tags", response_model=CompletedAlbum)
def update_album_user_tags(repository: DefaultAlbumRepository, album_id: int, request: UserAlbumTagsUpdate) -> dict:
    try:
        return update_manual_album_tags(repository, album_id, request.your_tags)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put("/{album_id}/your-feedback", response_model=CompletedAlbum)
def update_album_user_feedback(repository: DefaultAlbumRepository, album_id: int, request: UserAlbumFeedbackUpdate) -> dict:
    try:
        return update_manual_album_feedback(
            repository,
            album_id,
            rating=request.rating,
            notes=request.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
