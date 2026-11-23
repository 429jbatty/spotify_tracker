"""Run a queued Spotify ZIP import through its persisted checkpoints."""

import structlog
from sqlalchemy.orm import Session
from structlog.contextvars import bind_contextvars

from backend.app.config import get_settings
from backend.app.models import ImportSession
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories import spotify_import_repository as import_spotify
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary
from backend.app.services.spotify_import_parser import (
    spotify_history_entries_from_zip,
    spotify_zip_member_count,
)

from .candidate_results import summarize_candidates
from .candidate_workflow import finish_import_from_candidates
from .common import SPOTIFY_IMPORT_SOURCE
from .matching import AlbumCandidate
from .progress import (
    ImportMetadataStats,
    ImportStageTimer,
    TERMINAL_IMPORT_STATUSES,
    append_import_log,
    empty_summary,
    set_import_progress,
)
from .spotify_candidates import build_spotify_candidates_from_plays
from .spotify_recovery import resume_spotify_import_session
from .spotify_source import (
    delete_file_quietly,
    resolve_spotify_catalog_for_import,
    store_streaming_events,
)


def run_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    artifact_path = import_session.artifact_path
    existing_raw_events = import_spotify.event_count(session, repository.user.id, import_session.id)
    existing_import_rows = import_events.session_event_count(
        session, repository.user.id, import_session.id,
    )
    if existing_raw_events and (
        not artifact_path
        or import_session.status in {"fetching_metadata", "finalizing"}
        or existing_import_rows
    ):
        # Resumed summaries may exclude candidates processed before interruption.
        bind_contextvars(candidate_summary_scope="resume_subset")
        structlog.get_logger(__name__).info("import_resumed", source=SPOTIFY_IMPORT_SOURCE, previous_status=import_session.status)
        resume_spotify_import_session(session, repository, import_session)
        return
    if not artifact_path:
        raise ValueError("Spotify import ZIP is missing; re-upload is required.")

    summary = empty_summary()
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    try:
        import_session.status = "validating_zip"
        timer.start("validating_zip")
        set_import_progress(
            import_session,
            summary,
            label="Validating Spotify ZIP",
            current=0,
            total=0,
        )
        append_import_log(
            session,
            import_session,
            stage="validating_zip",
            message="Validating Spotify ZIP.",
        )
        session.commit()

        settings = get_settings()
        history_entries = spotify_history_entries_from_zip(
            artifact_path,
            max_entries=settings.spotify_import_max_zip_entries,
            max_uncompressed_bytes=settings.spotify_import_max_uncompressed_bytes,
        )
        import_session.zip_member_count = spotify_zip_member_count(artifact_path)
        timer.finish()
        summary.total_rows = len(history_entries)
        summary.spotify_import_original_filename = import_session.original_filename
        summary.spotify_import_file_size_bytes = import_session.file_size_bytes
        summary.spotify_import_sha256 = import_session.file_sha256
        summary.spotify_import_zip_member_count = import_session.zip_member_count
        summary.spotify_import_duplicate_of_session_id = (
            import_session.duplicate_of_import_session_id
        )
        set_import_progress(
            import_session,
            summary,
            label="Parsing Spotify history",
            current=0,
            total=len(history_entries),
        )
        import_session.status = "parsing_spotify_history"
        # This stage only prepares files; streaming JSON parsing happens during storage.
        timer.start("preparing_spotify_history")
        append_import_log(
            session,
            import_session,
            stage="parsing_spotify_history",
            message="Parsing Spotify history files.",
            current=0,
            total=len(history_entries),
        )
        session.commit()

        for index, entry in enumerate(history_entries, start=1):
            set_import_progress(
                import_session,
                summary,
                label="Parsing Spotify history",
                current=index,
                total=len(history_entries),
            )
            session.commit()

        timer.finish()
        set_import_progress(
            import_session,
            summary,
            label="Storing Spotify plays",
            current=0,
            total=0,
        )
        import_session.status = "storing_streaming_events"
        timer.start("storing_streaming_events")
        append_import_log(
            session,
            import_session,
            stage="storing_streaming_events",
            message="Storing Spotify plays.",
        )
        session.commit()

        def update_store_progress(summary_update: ImportPreviewSummary) -> None:
            if (
                summary_update.total_rows != summary_update.progress_current
                and summary_update.progress_current % 1000 != 0
            ):
                return
            set_import_progress(
                import_session,
                summary_update,
                label="Storing Spotify plays",
                current=summary_update.progress_current,
                total=summary_update.progress_total,
            )
            session.commit()

        summary = store_streaming_events(
            session=session,
            repository=repository,
            import_session=import_session,
            artifact_path=artifact_path,
            history_entries=history_entries,
            progress_callback=update_store_progress,
        )
        summary.stage_timings = dict(timer.summary.stage_timings or {})
        timer.summary = summary
        timer.finish()

        import_session.status = "resolving_spotify_catalog"
        set_import_progress(
            import_session,
            summary,
            label="Resolving Spotify catalog tracks",
            current=0,
            total=0,
        )
        timer.start("resolving_spotify_catalog")
        append_import_log(
            session,
            import_session,
            stage="resolving_spotify_catalog",
            message="Resolving Spotify track and album metadata.",
        )
        session.commit()
        resolve_spotify_catalog_for_import(
            session=session,
            repository=repository,
            import_session=import_session,
            summary=summary,
        )
        timer.finish()
        import_session.summary_json = summary.model_dump()
        session.commit()

        import_session.status = "grouping_album_sessions"
        set_import_progress(
            import_session,
            summary,
            label="Grouping album sessions",
            current=0,
            total=0,
        )
        append_import_log(
            session,
            import_session,
            stage="grouping_album_sessions",
            message="Grouping Spotify plays into album sessions.",
        )
        session.commit()

        import_session.status = "matching_cached_albums"
        # Candidate construction combines grouping and cached matching in one pass.
        timer.start("matching_cached_albums")
        append_import_log(
            session,
            import_session,
            stage="matching_cached_albums",
            message="Checking saved album metadata.",
        )

        def update_cached_match_progress(
            current: int,
            total: int,
            partial_candidates: list[AlbumCandidate],
        ) -> None:
            summarize_candidates(summary, partial_candidates)
            set_import_progress(
                import_session,
                summary,
                label="Matching cached albums",
                current=current,
                total=total,
            )
            session.commit()

        cached_candidates = build_spotify_candidates_from_plays(
            session=session,
            repository=repository,
            import_session=import_session,
            allow_remote_metadata=False,
            metadata_stats=metadata_stats,
            progress_callback=update_cached_match_progress,
        )
        timer.finish()
        finish_import_from_candidates(
            session, repository, import_session, cached_candidates, summary, metadata_stats, timer,
        )
    finally:
        if import_session.status in TERMINAL_IMPORT_STATUSES:
            delete_file_quietly(artifact_path)
            import_session.artifact_path = None
        session.commit()
