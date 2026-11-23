"""Run a queued Last.fm import or resume its pending metadata work."""

import structlog
from sqlalchemy.orm import Session
from structlog.contextvars import bind_contextvars

from backend.app.models import ImportSession, ImportedListeningEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.lastfm_import_client import fetch_lastfm_recent_tracks

from .candidate_results import log_candidate_outcomes, summarize_candidates
from .candidate_workflow import enrich_pending_albums, finish_import_from_candidates
from .lastfm_candidates import build_lastfm_candidates_from_rows
from .lastfm_source import lastfm_api_key, lastfm_raw_import_summary, persist_lastfm_raw_events
from .matching import AlbumCandidate
from .progress import (
    ImportMetadataStats,
    ImportStageTimer,
    append_import_log,
    apply_metadata_stats,
    empty_summary,
    session_summary,
    set_import_progress,
    stage_completed_import,
)


def run_lastfm_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    source_user_id = import_session.source_user_id
    api_key = lastfm_api_key()
    if import_session.status in {"fetching_metadata", "finalizing"}:
        pending_rows = import_events.pending_metadata(
            session, repository.user.id, import_session.id,
        )
        if pending_rows:
            # Resumed summaries cover pending candidates, not the entire import.
            bind_contextvars(candidate_summary_scope="resume_subset")
            structlog.get_logger(__name__).info("import_resumed", source="lastfm", previous_status=import_session.status)
            _resume_lastfm_metadata_import(session, repository, import_session, pending_rows)
            return

    import_session.status = "fetching_lastfm"
    append_import_log(
        session,
        import_session,
        stage="fetching_lastfm",
        message="Fetching Last.fm scrobbles.",
    )
    session.commit()

    fetch_summary = empty_summary()
    timer = ImportStageTimer(import_session.id, fetch_summary)
    timer.start("fetching_lastfm")
    metadata_stats = ImportMetadataStats()

    def update_fetch_progress(
        *,
        page: int,
        total_pages: int,
        rows_fetched: int,
        total_available: int | None,
    ) -> None:
        if page != 1 and page % 5 != 0 and page != total_pages:
            return
        total = total_available or max(total_pages * 200, rows_fetched)
        fetch_summary.total_rows = total
        set_import_progress(
            import_session,
            fetch_summary,
            label="Fetching Last.fm scrobbles",
            current=rows_fetched,
            total=total,
        )
        session.commit()

    fetch_result = fetch_lastfm_recent_tracks(
        source_user_id or "",
        api_key,
        import_events.latest_timestamp(
            session,
            repository.user.id,
            "lastfm",
            source_user_id=source_user_id,
        ),
        progress_callback=update_fetch_progress,
    )

    rows = fetch_result.rows
    timer.finish()
    summary = lastfm_raw_import_summary(rows, [])
    timer.summary = summary
    if fetch_result.total_available is not None:
        summary.total_rows = fetch_result.total_available
    set_import_progress(
        import_session,
        summary,
        label="Storing scrobbles",
        current=0,
        total=len(rows),
    )
    import_session.status = "storing_scrobbles"
    timer.start("storing_scrobbles")
    append_import_log(
        session,
        import_session,
        stage="storing_scrobbles",
        message="Storing Last.fm scrobbles.",
        current=0,
        total=len(rows),
    )
    session.commit()

    def update_store_progress(processed: int, total: int, persisted: int) -> None:
        if processed != total and processed % 500 != 0:
            return
        summary.new_event_rows = persisted
        set_import_progress(
            import_session,
            summary,
            label="Storing scrobbles",
            current=processed,
            total=total,
        )
        session.commit()

    raw_rows = persist_lastfm_raw_events(
        session=session,
        repository=repository,
        import_session=import_session,
        rows=rows,
        source_user_id=source_user_id,
        progress_callback=update_store_progress,
    )
    previous_timings = dict(summary.stage_timings or {})
    summary = lastfm_raw_import_summary(rows, raw_rows)
    summary.stage_timings = previous_timings
    timer.summary = summary
    timer.finish()
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
        message="Grouping Last.fm scrobbles into album sessions.",
    )
    session.commit()

    candidate_rows = [row for row in raw_rows if row.match_status == "raw_imported"]
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

    cached_candidates = build_lastfm_candidates_from_rows(
        session=session,
        repository=repository,
        imported_rows=candidate_rows,
        allow_remote_metadata=False,
        metadata_stats=metadata_stats,
        progress_callback=update_cached_match_progress,
    )
    timer.finish()
    finish_import_from_candidates(
        session, repository, import_session, cached_candidates, summary, metadata_stats, timer,
    )


def _resume_lastfm_metadata_import(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    pending_rows: list[ImportedListeningEvent],
) -> None:
    summary = session_summary(import_session)
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    append_import_log(
        session,
        import_session,
        stage="fetching_metadata",
        message="Resuming Last.fm import from pending metadata candidates.",
    )
    import_session.status = "fetching_metadata"
    timer.start("fetching_metadata")
    remote_candidates = enrich_pending_albums(
        session=session,
        repository=repository,
        import_session=import_session,
        pending_rows=pending_rows,
        cached_candidates=[],
        summary=summary,
        metadata_stats=metadata_stats,
    )
    timer.finish()
    summarize_candidates(summary, remote_candidates)
    log_candidate_outcomes(remote_candidates, scope="resume_subset")
    apply_metadata_stats(summary, metadata_stats)
    import_session.status = "finalizing"
    set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(remote_candidates),
        total=summary.progress_total or len(remote_candidates),
    )
    session.commit()
    stage_completed_import(
        session, import_session, summary, candidate_count=len(remote_candidates),
        message="Last.fm import completed after resume.",
    )
    session.commit()
