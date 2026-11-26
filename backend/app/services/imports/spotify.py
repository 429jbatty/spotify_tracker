"""Run Spotify ZIP imports and recover or repair them from persisted evidence."""

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models import ImportSession
from backend.app.repositories import (
    import_event_repository as import_events,
    import_session_repository as import_sessions,
    spotify_import_repository as import_spotify,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportSessionSummary
from backend.app.services.spotify_import_parser import (
    spotify_history_entries_from_zip,
    spotify_zip_member_count,
)

from .candidate_results import apply_candidate_results, summarize_candidates
from .candidate_workflow import (
    ImportRun,
    apply_cached_matches,
    complete,
    enrich_pending_albums,
    finalizing_checkpoint,
    finish_import,
    report_outcomes,
)
from .events import SPOTIFY_IMPORT_SOURCE
from .progress import (
    TERMINAL_IMPORT_STATUSES,
    build_import_session_summary,
    session_summary,
    set_import_progress,
)
from .spotify_candidates import build_spotify_candidates_from_plays, rebuild_spotify_candidates_from_rows
from .spotify_source import delete_file_quietly, resolve_spotify_catalog_for_import, store_streaming_events


def run_spotify_import_session(session: Session, repository: SqliteStateRepository, import_session: ImportSession) -> None:
    path = import_session.artifact_path
    user_id = repository.user.id
    raw_count = import_spotify.event_count(session, user_id, import_session.id)
    candidate_count = import_events.session_event_count(session, user_id, import_session.id)
    run = ImportRun(session, repository, import_session)
    if raw_count and (not path or candidate_count or import_session.status in {"fetching_metadata", "finalizing"}):
        run.resumed()
        run.summary = session_summary(import_session)
        resume_spotify_import_session(run)
        return
    if not path:
        raise ValueError("Spotify import ZIP is missing; re-upload is required.")

    try:
        _ingest_zip(run, path)
        resolve_catalog(run, resumed=False)
        run.grouped("Spotify plays")
        candidates = build_spotify_candidates_from_plays(
            session, repository, import_session, allow_remote_metadata=False,
            metadata_stats=run.stats, progress_callback=run.matching_progress,
        )
        apply_cached_matches(run, candidates)
        finish_import(run, candidates)
    finally:
        if import_session.status in TERMINAL_IMPORT_STATUSES:
            delete_file_quietly(path)
            import_session.artifact_path = None
        session.commit()


def _ingest_zip(run: ImportRun, path):
    run.start("validating_zip")
    run.progress("Validating Spotify ZIP")
    run.log("Validating Spotify ZIP.")
    run.db.commit()

    settings = get_settings()
    entries = spotify_history_entries_from_zip(
        path, max_entries=settings.spotify_import_max_zip_entries,
        max_uncompressed_bytes=settings.spotify_import_max_uncompressed_bytes,
    )
    run.row.zip_member_count = spotify_zip_member_count(path)
    run.finish_stage()
    timings = run.summary.stage_timings
    run.summary = session_summary(run.row)
    run.summary.stage_timings = timings
    run.summary.total_rows = len(entries)
    run.progress("Parsing Spotify history", 0, len(entries))
    run.start("parsing_spotify_history", timing="preparing_spotify_history")
    run.log("Parsing Spotify history files.", current=0, total=len(entries))
    run.db.commit()
    for current in range(1, len(entries) + 1):
        run.progress("Parsing Spotify history", current, len(entries))
        run.db.commit()

    run.finish_stage()
    run.progress("Storing Spotify plays")
    run.start("storing_streaming_events")
    run.log("Storing Spotify plays.")
    run.db.commit()

    def stored(summary):
        # The parser reports every source row, including rejected and duplicate plays.
        set_import_progress(run.row, summary, label="Storing Spotify plays",
                            current=summary.progress_current, total=summary.progress_total)
        run.db.commit()

    summary = store_streaming_events(run.db, run.library, run.row, path, entries, stored)
    summary.stage_timings = run.summary.stage_timings
    run.summary = summary
    run.finish_stage()


def repair_spotify_import_session(
    session: Session, repository: SqliteStateRepository, import_session_id: int,
) -> ImportSessionSummary:
    user_id = repository.user.id
    row = import_sessions.get_for_user(session, user_id, import_session_id)
    if row is None:
        raise KeyError(f"Import session not found: {import_session_id}")
    if row.source != SPOTIFY_IMPORT_SOURCE:
        raise ValueError("Only Spotify import sessions can be repaired.")
    raw = import_events.raw_spotify_candidates(session, user_id, row.id)
    if not raw:
        return build_import_session_summary(row)
    if import_events.count_spotify_candidates(session, user_id, row.id, "processed_album_listen"):
        raise ValueError("Refusing to repair a mixed Spotify import session with both raw and processed candidates.")

    run = ImportRun(session, repository, row, session_summary(row))
    run.log("Repairing Spotify import candidates that were left raw after resume.",
            stage="repair", current=0, total=len(raw))
    candidates = _apply_persisted_candidates(run, raw)
    _finish_recovery(run, candidates, "Spotify import repaired.")
    return build_import_session_summary(row)


def resume_spotify_import_session(run: ImportRun) -> None:
    run.log("Resuming Spotify import from persisted progress.")
    candidate_count = import_events.session_event_count(run.db, run.library.user.id, run.row.id)
    raw = import_events.raw_spotify_candidates(run.db, run.library.user.id, run.row.id)
    if not candidate_count:
        resolve_catalog(run, resumed=True)
        run.start("matching_cached_albums")
        run.progress("Matching cached albums")
        run.db.commit()
        candidates = build_spotify_candidates_from_plays(
            run.db, run.library, run.row, allow_remote_metadata=False, metadata_stats=run.stats,
        )
        apply_cached_matches(run, candidates, flush=False)
    elif raw:
        candidates = _apply_persisted_candidates(run, raw)
    else:
        candidates = []

    _finish_recovery(run, candidates, "Spotify import completed after resume.")
    if run.row.artifact_path:
        delete_file_quietly(run.row.artifact_path)
        run.row.artifact_path = None
    run.db.commit()


def _apply_persisted_candidates(run, rows):
    run.start("matching_cached_albums")
    run.progress("Matching cached albums", 0, len(rows))
    run.db.commit()
    candidates = rebuild_spotify_candidates_from_rows(
        run.db, run.library, rows, allow_remote_metadata=False, metadata_stats=run.stats,
    )
    apply_candidate_results(run.db, run.library, candidates)
    summarize_candidates(run.summary, candidates)
    run.stats.apply(run.summary)
    run.progress("Matching cached albums", len(rows), len(rows))
    run.log("Processed persisted Spotify album-session candidates.", current=len(rows), total=len(rows))
    run.db.commit()
    run.finish_stage()
    return candidates


def resolve_catalog(run: ImportRun, *, resumed):
    run.start("resolving_spotify_catalog")
    resolved = run.summary.spotify_catalog_resolved_tracks if resumed else 0
    total = resolved + run.summary.spotify_catalog_unresolved_tracks if resumed else 0
    run.progress("Resolving Spotify catalog tracks", resolved, total)
    if not resumed:
        run.log("Resolving Spotify track and album metadata.")
    run.db.commit()
    resolve_spotify_catalog_for_import(run.db, run.library, run.row, run.summary)
    run.finish_stage()
    run.row.summary_json = run.summary.model_dump()
    run.db.commit()


def _finish_recovery(run, candidates, message):
    pending = run.pending_metadata()
    if pending:
        run.start("fetching_metadata")
        candidates = enrich_pending_albums(run, pending, candidates)
        run.finish_stage()
        summarize_candidates(run.summary, candidates)
        run.stats.apply(run.summary)
        run.db.commit()
    remaining = import_events.count_spotify_candidates(run.db, run.row.user_id, run.row.id, "raw_imported")
    if remaining:
        raise ValueError(f"Spotify import still has {remaining} unprocessed candidate rows.")
    run.start("finalizing")
    report_outcomes(run, candidates, "resume_or_repair_subset")
    finalizing_checkpoint(run, candidates)
    run.finish_stage()
    complete(run, candidates, message)
