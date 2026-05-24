import threading
import logging

from fastapi import APIRouter, HTTPException, status
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
    ImportSessionSummary,
)
from backend.app.services import import_service


router = APIRouter(prefix="/users/{user_slug}/imports", tags=["imports"])
logger = logging.getLogger(__name__)


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
        logger.exception("Last.fm import session %s failed.", import_session_id)


def _start_import_background_worker(import_session_id: int) -> None:
    thread = threading.Thread(
        target=_run_import_background_worker,
        args=(import_session_id,),
        daemon=True,
    )
    thread.start()


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


@router.get("", response_model=list[ImportSessionSummary])
def list_user_imports(user_slug: str) -> list[ImportSessionSummary]:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            repository = SqliteStateRepository(session, user_slug=user_slug)
            return import_service.import_history(session, repository)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


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
