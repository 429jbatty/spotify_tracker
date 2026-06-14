import threading
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    CompletedAlbum,
    ImportCommitResponse,
    ImportDeleteResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportResolveRequest,
    ImportReviewItem,
    SpotifyImportDiagnosticsResponse,
    ImportSessionLogEntry,
    ImportSessionSummary,
)
from backend.app.services import import_service


router = APIRouter(prefix="/users/{user_slug}/imports", tags=["imports"])
logger = logging.getLogger(__name__)
SPOTIFY_ZIP_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}


def _session_factory():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _run_import_background_worker(import_session_id: int) -> None:
    session_factory = _session_factory()
    try:
        with session_factory() as session:
            import_service.run_import_session(session, import_session_id)
    except Exception:
        logger.exception("Import session %s failed.", import_session_id)


def _start_import_background_worker(import_session_id: int) -> None:
    thread = threading.Thread(
        target=_run_import_background_worker,
        args=(import_session_id,),
        daemon=True,
    )
    thread.start()


def resume_interrupted_imports() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        import_session_ids = import_service.resumable_import_session_ids(session)
    for import_session_id in import_session_ids:
        logger.info("Auto-resuming import session %s.", import_session_id)
        _start_import_background_worker(import_session_id)


@router.post("/preview", response_model=ImportPreviewResponse)
def preview_user_import(
    user_slug: str,
    request: ImportPreviewRequest,
) -> ImportPreviewResponse:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.preview_import(session, repository, request)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/commit", response_model=ImportCommitResponse)
def commit_user_import(
    user_slug: str,
    request: ImportPreviewRequest,
) -> ImportCommitResponse:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            response = import_service.commit_import(session, repository, request)
            _start_import_background_worker(response.import_session_id)
            return response
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/spotify/upload", response_model=ImportCommitResponse)
async def upload_spotify_import(
    user_slug: str,
    file: UploadFile = File(...),
) -> ImportCommitResponse:
    artifact_path: Path | None = None
    session_factory = _session_factory()
    try:
        artifact_path = await _store_spotify_zip_upload(file)
        with session_factory() as session:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            response = import_service.create_spotify_import_session(
                session,
                repository,
                artifact_path=str(artifact_path),
                original_filename=file.filename,
            )
            _start_import_background_worker(response.import_session_id)
            return response
    except KeyError as exc:
        if artifact_path:
            artifact_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        if artifact_path:
            artifact_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("", response_model=list[ImportSessionSummary])
def list_user_imports(user_slug: str) -> list[ImportSessionSummary]:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.import_history(session, repository)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{import_session_id}/logs", response_model=list[ImportSessionLogEntry])
def list_user_import_logs(
    user_slug: str,
    import_session_id: int,
    limit: int = 100,
    order: str = "asc",
) -> list[ImportSessionLogEntry]:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.import_session_logs(
                session,
                repository,
                import_session_id,
                limit=limit,
                order=order,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{import_session_id}/diagnostics", response_model=SpotifyImportDiagnosticsResponse)
def get_spotify_import_diagnostics(
    user_slug: str,
    import_session_id: int,
    artist: str,
    album: str,
) -> SpotifyImportDiagnosticsResponse:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.spotify_import_diagnostics(
                session,
                repository,
                import_session_id,
                artist=artist,
                album=album,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


async def _store_spotify_zip_upload(file: UploadFile) -> Path:
    settings = get_settings()
    filename = file.filename or ""
    if not filename.casefold().endswith(".zip"):
        raise ValueError("Upload a Spotify .zip file.")
    if file.content_type and file.content_type not in SPOTIFY_ZIP_CONTENT_TYPES:
        raise ValueError("Upload must be a ZIP archive.")

    upload_dir = Path(settings.data_dir) / "import_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = upload_dir / f"spotify-{uuid.uuid4().hex}.zip"
    max_bytes = settings.spotify_import_max_zip_bytes
    bytes_written = 0

    try:
        with artifact_path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise ValueError("Spotify ZIP upload is too large.")
                output.write(chunk)
    except Exception:
        artifact_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if bytes_written == 0:
        artifact_path.unlink(missing_ok=True)
        raise ValueError("Spotify ZIP upload is empty.")

    return artifact_path


@router.get("/review", response_model=list[ImportReviewItem])
def list_user_import_review(user_slug: str) -> list[ImportReviewItem]:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.unresolved_review_items(session, repository)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/review/{review_item_id}/resolve", response_model=CompletedAlbum)
def resolve_user_import_review(
    user_slug: str,
    review_item_id: int,
    request: ImportResolveRequest,
) -> CompletedAlbum:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.resolve_review_item(
                session,
                repository,
                review_item_id,
                request,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.delete("/{import_session_id}", response_model=ImportDeleteResponse)
def delete_user_import(
    user_slug: str,
    import_session_id: int,
) -> ImportDeleteResponse:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.delete_import_session(
                session,
                repository,
                import_session_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
