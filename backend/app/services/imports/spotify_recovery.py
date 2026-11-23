"""Resume or repair a Spotify import from its persisted plays and candidates."""

from sqlalchemy.orm import Session

from backend.app.models import ImportSession, ImportedListeningEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories import import_session_repository as import_sessions
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary, ImportSessionSummary

from .candidate_results import (
    apply_candidate_results,
    log_candidate_outcomes,
    summarize_candidates,
)
from .candidate_workflow import enrich_pending_albums
from .common import SPOTIFY_IMPORT_SOURCE
from .matching import AlbumCandidate
from .progress import (
    ImportMetadataStats,
    ImportStageTimer,
    append_import_log,
    apply_metadata_stats,
    build_import_session_summary,
    session_summary,
    set_import_progress,
    stage_completed_import,
)
from .spotify_candidates import (
    build_spotify_candidates_from_plays,
    rebuild_spotify_candidates_from_rows,
)
from .spotify_source import delete_file_quietly, resolve_spotify_catalog_for_import


def repair_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
) -> ImportSessionSummary:
    import_session = import_sessions.get_for_user(session, repository.user.id, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")
    if import_session.source != SPOTIFY_IMPORT_SOURCE:
        raise ValueError("Only Spotify import sessions can be repaired.")

    raw_rows = import_events.raw_spotify_candidates(session, repository.user.id, import_session.id)
    if not raw_rows:
        return build_import_session_summary(import_session)

    processed_count = import_events.count_spotify_candidates(
        session, repository.user.id, import_session.id, "processed_album_listen",
    )
    if processed_count:
        raise ValueError(
            "Refusing to repair a mixed Spotify import session with both raw and processed candidates."
        )

    summary = session_summary(import_session)
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    append_import_log(
        session,
        import_session,
        stage="repair",
        message="Repairing Spotify import candidates that were left raw after resume.",
        current=0,
        total=len(raw_rows),
    )
    import_session.status = "matching_cached_albums"
    timer.start("matching_cached_albums")
    cached_candidates = _process_existing_spotify_candidate_rows(
        session=session,
        repository=repository,
        import_session=import_session,
        raw_rows=raw_rows,
        summary=summary,
        metadata_stats=metadata_stats,
    )
    timer.finish()
    final_candidates = _process_spotify_pending_metadata_for_resume(
        session=session,
        repository=repository,
        import_session=import_session,
        cached_candidates=cached_candidates,
        summary=summary,
        metadata_stats=metadata_stats,
        timer=timer,
    )
    _finalize_spotify_resume_or_repair(
        session=session,
        import_session=import_session,
        summary=summary,
        metadata_stats=metadata_stats,
        final_candidates=final_candidates,
        timer=timer,
        completed_message="Spotify import repaired.",
    )
    return build_import_session_summary(import_session)


def resume_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    summary = session_summary(import_session)
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    append_import_log(
        session,
        import_session,
        stage=import_session.status,
        message="Resuming Spotify import from persisted progress.",
    )

    imported_count = import_events.session_event_count(
        session, repository.user.id, import_session.id,
    )
    raw_candidate_rows = import_events.raw_spotify_candidates(
        session, repository.user.id, import_session.id,
    )
    if imported_count == 0:
        import_session.status = "resolving_spotify_catalog"
        timer.start("resolving_spotify_catalog")
        set_import_progress(
            import_session,
            summary,
            label="Resolving Spotify catalog tracks",
            current=summary.spotify_catalog_resolved_tracks,
            total=summary.spotify_catalog_resolved_tracks
            + summary.spotify_catalog_unresolved_tracks,
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

        import_session.status = "matching_cached_albums"
        timer.start("matching_cached_albums")
        set_import_progress(
            import_session,
            summary,
            label="Matching cached albums",
            current=0,
            total=0,
        )
        session.commit()
        cached_candidates = build_spotify_candidates_from_plays(
            session=session,
            repository=repository,
            import_session=import_session,
            allow_remote_metadata=False,
            metadata_stats=metadata_stats,
        )
        timer.finish()
        summarize_candidates(summary, cached_candidates)
        apply_metadata_stats(summary, metadata_stats)
        apply_candidate_results(
            session=session,
            repository=repository,
            candidates=cached_candidates,
        )
        session.commit()
    elif raw_candidate_rows:
        import_session.status = "matching_cached_albums"
        timer.start("matching_cached_albums")
        cached_candidates = _process_existing_spotify_candidate_rows(
            session=session,
            repository=repository,
            import_session=import_session,
            raw_rows=raw_candidate_rows,
            summary=summary,
            metadata_stats=metadata_stats,
        )
        timer.finish()
    else:
        cached_candidates = []

    final_candidates = _process_spotify_pending_metadata_for_resume(
        session=session,
        repository=repository,
        import_session=import_session,
        cached_candidates=cached_candidates,
        summary=summary,
        metadata_stats=metadata_stats,
        timer=timer,
    )

    _finalize_spotify_resume_or_repair(
        session=session,
        import_session=import_session,
        summary=summary,
        metadata_stats=metadata_stats,
        final_candidates=final_candidates,
        timer=timer,
        completed_message="Spotify import completed after resume.",
    )

    if import_session.artifact_path:
        delete_file_quietly(import_session.artifact_path)
        import_session.artifact_path = None
    session.commit()


def _process_existing_spotify_candidate_rows(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    raw_rows: list[ImportedListeningEvent],
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
) -> list[AlbumCandidate]:
    set_import_progress(
        import_session,
        summary,
        label="Matching cached albums",
        current=0,
        total=len(raw_rows),
    )
    session.commit()
    candidates = rebuild_spotify_candidates_from_rows(
        session=session,
        repository=repository,
        imported_rows=raw_rows,
        allow_remote_metadata=False,
        metadata_stats=metadata_stats,
    )
    apply_candidate_results(
        session=session,
        repository=repository,
        candidates=candidates,
    )
    summarize_candidates(summary, candidates)
    apply_metadata_stats(summary, metadata_stats)
    set_import_progress(
        import_session,
        summary,
        label="Matching cached albums",
        current=len(raw_rows),
        total=len(raw_rows),
    )
    append_import_log(
        session,
        import_session,
        stage="matching_cached_albums",
        message="Processed persisted Spotify album-session candidates.",
        current=len(raw_rows),
        total=len(raw_rows),
    )
    session.commit()
    return candidates


def _process_spotify_pending_metadata_for_resume(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    cached_candidates: list[AlbumCandidate],
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
    timer: ImportStageTimer,
) -> list[AlbumCandidate]:
    pending_rows = import_events.pending_metadata(session, repository.user.id, import_session.id)
    if not pending_rows:
        return cached_candidates

    import_session.status = "fetching_metadata"
    timer.start("fetching_metadata")
    final_candidates = enrich_pending_albums(
        session=session,
        repository=repository,
        import_session=import_session,
        pending_rows=pending_rows,
        cached_candidates=cached_candidates,
        summary=summary,
        metadata_stats=metadata_stats,
    )
    timer.finish()
    summarize_candidates(summary, final_candidates)
    apply_metadata_stats(summary, metadata_stats)
    session.commit()
    return final_candidates


def _finalize_spotify_resume_or_repair(
    session: Session,
    import_session: ImportSession,
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
    final_candidates: list[AlbumCandidate],
    timer: ImportStageTimer,
    completed_message: str,
) -> None:
    raw_remaining = import_events.count_spotify_candidates(
        session, import_session.user_id, import_session.id, "raw_imported",
    )
    if raw_remaining:
        raise ValueError(
            f"Spotify import still has {raw_remaining} unprocessed candidate rows."
        )

    import_session.status = "finalizing"
    timer.start("finalizing")
    summarize_candidates(summary, final_candidates)
    log_candidate_outcomes(final_candidates, scope="resume_or_repair_subset")
    apply_metadata_stats(summary, metadata_stats)
    set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    session.commit()

    timer.finish()
    stage_completed_import(
        session, import_session, summary, candidate_count=len(final_candidates),
        message=completed_message,
    )
    session.commit()
