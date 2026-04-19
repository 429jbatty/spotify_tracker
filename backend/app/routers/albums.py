from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import sessionmaker

import metadata_refresh_service
from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    AlbumListenCreate,
    AlbumMergeRequest,
    AlbumMetadataUpdate,
    AlbumRefreshRequest,
    CompletedAlbum,
    ManualAlbumCreate,
)

router = APIRouter(prefix="/albums", tags=["albums"])


DUPLICATE_KEY_PREFIX = "Album key already exists: "


def _repository():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    return session, SqliteStateRepository(session)


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
    album_id: int,
    request: AlbumRefreshRequest | None = None,
) -> dict:
    session, repository = _repository()
    try:
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
    finally:
        session.close()


@router.post("", response_model=CompletedAlbum, status_code=status.HTTP_201_CREATED)
def create_album(request: ManualAlbumCreate) -> dict:
    session, repository = _repository()
    try:
        record = request.model_dump(exclude={"listen_date"})
        return repository.create_completed_album(
            record,
            listen_date=request.listen_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    finally:
        session.close()


@router.patch("/{album_id}", response_model=CompletedAlbum)
def update_album(album_id: int, request: AlbumMetadataUpdate) -> dict:
    fields = request.model_dump(exclude_unset=True)
    session, repository = _repository()
    try:
        return repository.update_completed_album_fields(album_id, fields)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_duplicate_album_detail(repository, exc),
        )
    finally:
        session.close()


@router.post("/{album_id}/listens", response_model=CompletedAlbum)
def add_album_listen(album_id: int, request: AlbumListenCreate) -> dict:
    session, repository = _repository()
    try:
        return repository.add_album_listen(album_id, request.listened_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    finally:
        session.close()


@router.post("/{album_id}/merge", response_model=CompletedAlbum)
def merge_album(album_id: int, request: AlbumMergeRequest) -> dict:
    session, repository = _repository()
    try:
        return repository.merge_completed_album_listens(
            album_id,
            request.target_album_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    finally:
        session.close()


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(album_id: int) -> None:
    session, repository = _repository()
    try:
        repository.delete_completed_album(album_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    finally:
        session.close()
