"""Public import entry points and background worker dispatch."""

import time

import structlog
from sqlalchemy.orm import Session
from structlog.contextvars import bound_contextvars, get_contextvars

from backend.app.config import get_settings
from backend.app.models import ImportSession
from backend.app.persistence_logging import database_error_fields
from backend.app.repositories import import_session_repository as import_sessions
from backend.app.repositories.import_event_repository import latest_timestamp as latest_imported_timestamp
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportSessionSummary
from backend.app.services.artwork_backfill_service import ArtworkBackfillService
from backend.app.services.imports.events import SPOTIFY_IMPORT_SOURCE, utc_now
from backend.app.services.imports.history import delete_import_session, import_history, import_session_logs
from backend.app.services.imports.lastfm import commit_import, preview_import, run_lastfm_import_session
from backend.app.services.imports.progress import (
    append_import_log,
    build_import_session_summary,
    session_summary,
    set_import_progress,
)
from backend.app.services.imports.review import resolve_review_item, unresolved_review_items
from backend.app.services.imports.spotify import repair_spotify_import_session, run_spotify_import_session
from backend.app.services.imports.spotify_diagnostics import spotify_import_diagnostics
from backend.app.services.imports.spotify_source import create_spotify_import_session


__all__ = [
    "preview_import",
    "commit_import",
    "create_spotify_import_session",
    "run_import_session",
    "resumable_import_session_ids",
    "repair_spotify_import_session",
    "import_history",
    "import_session_logs",
    "spotify_import_diagnostics",
    "unresolved_review_items",
    "resolve_review_item",
    "delete_import_session",
    "latest_imported_timestamp",
]


POST_IMPORT_ARTWORK_BACKFILL_LIMIT = 100
RESUMABLE_IMPORT_STATUSES = {
    "queued",
    "validating_zip",
    "parsing_spotify_history",
    "storing_streaming_events",
    "resolving_spotify_catalog",
    "fetching_lastfm",
    "storing_scrobbles",
    "grouping_album_sessions",
    "matching_cached_albums",
    "fetching_metadata",
    "finalizing",
}


def run_import_session(session: Session, import_session_id: int) -> ImportSessionSummary:
    import_session = import_sessions.get_for_worker(session, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")

    started = time.perf_counter()
    with bound_contextvars(
        user_id=import_session.user_id, import_session_id=import_session_id,
        candidate_summary_scope="full_import",
    ):
        structlog.get_logger(__name__).info("import_started", source=import_session.source)
        repository = SqliteStateRepository(session, user_slug=import_session.user.slug)
        try:
            if import_session.source == "lastfm":
                run_lastfm_import_session(session, repository, import_session)
            elif import_session.source == SPOTIFY_IMPORT_SOURCE:
                run_spotify_import_session(session, repository, import_session)
            else:
                raise ValueError(f"Unsupported import source: {import_session.source}")
            _run_post_import_artwork_backfill(session, repository, import_session)
        except Exception as exc:
            database_fields = database_error_fields(exc)
            log_failure = structlog.get_logger(__name__).error if database_fields else structlog.get_logger(__name__).exception
            log_failure(
                "import_failed", stage=getattr(import_session, "status", "unknown"),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                **database_fields,
            )
            try:
                setattr(exc, "_albumary_import_logged", True)
            except (AttributeError, TypeError):
                pass
            summary = session_summary(import_session)
            import_sessions.finish_session(import_session, "failed", utc_now())
            append_import_log(
                session,
                import_session,
                level="error",
                stage=summary.progress_label,
                message="Import failed. Check server logs for traceback.",
            )
            set_import_progress(
                import_session,
                summary,
                label="Failed",
                current=summary.progress_current,
                total=summary.progress_total,
            )
            session.commit()
            raise

        summary = session_summary(import_session)
        fields = {
            "source": import_session.source,
            "status": import_session.status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "source_rows_reported": summary.total_rows,
            "new_source_rows": summary.new_event_rows,
            "candidate_summary_scope": get_contextvars()["candidate_summary_scope"],
            "album_session_candidates": summary.distinct_album_candidates,
            "matched_existing_candidates": summary.matched_existing_rows,
            "new_album_candidates": summary.new_album_rows,
            "derived_album_listens": summary.derived_album_listens,
            "review_candidates": summary.review_candidates,
            "pending_metadata_candidates": summary.pending_metadata_candidates,
            "metadata_cache_hits": summary.metadata_cache_hits,
            "metadata_cache_misses": summary.metadata_cache_misses,
            "musicbrainz_requests": summary.musicbrainz_requests,
        }
        if import_session.source == SPOTIFY_IMPORT_SOURCE:
            fields.update(
                duplicate_source_rows=summary.duplicate_rows,
                invalid_source_rows=summary.failed_rows,
                catalog_resolved_track_ids=summary.spotify_catalog_resolved_tracks,
                catalog_unresolved_track_ids=summary.spotify_catalog_unresolved_tracks,
                catalog_fallback_source_rows=summary.spotify_catalog_fallback_rows,
            )
        structlog.get_logger(__name__).info("import_finished", **fields)
        return build_import_session_summary(import_session)


def _run_post_import_artwork_backfill(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    if import_session.status != "completed":
        return

    try:
        album_ids = repository.album_ids_for_import_session_artwork_backfill(
            import_session.id,
        )
        if not album_ids:
            return

        append_import_log(
            session,
            import_session,
            stage="artwork_backfill",
            message="Checking imported albums for missing artwork.",
            metadata={
                "album_count": len(album_ids),
                "limit": POST_IMPORT_ARTWORK_BACKFILL_LIMIT,
            },
        )
        session.commit()

        service = ArtworkBackfillService(media_dir=get_settings().media_dir)
        summary, _ = service.backfill_missing_artwork(
            repository,
            apply=True,
            limit=POST_IMPORT_ARTWORK_BACKFILL_LIMIT,
            album_ids=album_ids,
        )
        append_import_log(
            session,
            import_session,
            stage="artwork_backfill",
            message="Artwork backfill completed.",
            metadata=summary.__dict__,
        )
        session.commit()
    except Exception as exc:
        # SQLAlchemy exceptions can embed statement parameters and credentials.
        error_fields = database_error_fields(exc)
        structlog.get_logger(__name__).warning(
            "post_import_artwork_backfill_failed", error_type=type(exc).__name__,
            **error_fields,
        )
        try:
            append_import_log(
                session,
                import_session,
                level="warning",
                stage="artwork_backfill",
                message="Artwork backfill failed; import remains completed.",
                metadata={"error_type": type(exc).__name__, **error_fields},
            )
            session.commit()
        except Exception as warning_exc:
            structlog.get_logger(__name__).warning(
                "post_import_artwork_warning_record_failed",
                error_type=type(warning_exc).__name__, **database_error_fields(warning_exc),
            )


def resumable_import_session_ids(session: Session) -> list[int]:
    return import_sessions.resumable_ids(session, RESUMABLE_IMPORT_STATUSES)
