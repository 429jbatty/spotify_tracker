"""Preview, queue and run Last.fm imports from raw scrobbles through album matching."""

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models import ImportSession
from backend.app.repositories import (
    import_event_repository as import_events,
    import_session_repository as import_sessions,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    ImportCommitResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportPreviewRow,
)
from backend.app.services.lastfm_import_client import fetch_lastfm_recent_tracks

from .candidate_workflow import (
    ImportRun,
    apply_cached_matches,
    complete,
    enrich_pending_albums,
    finalizing_checkpoint,
    finish_import,
    report_outcomes,
)
from .events import utc_now
from .lastfm_candidates import build_lastfm_candidates_from_rows, scrobble_fingerprint, scrobble_sessions
from .progress import append_import_log, commit_response, empty_summary, session_summary
from .track_matching import track_identity


def run_lastfm_import_session(session: Session, repository: SqliteStateRepository, import_session: ImportSession) -> None:
    api_key = lastfm_api_key()
    run = ImportRun(session, repository, import_session)
    if import_session.status in {"fetching_metadata", "finalizing"}:
        pending = run.pending_metadata()
        if pending:
            run.resumed()
            run.summary = session_summary(import_session)
            run.log("Resuming Last.fm import from pending metadata candidates.", stage="fetching_metadata")
            run.start("fetching_metadata")
            candidates = enrich_pending_albums(run, pending, [])
            run.finish_stage()
            report_outcomes(run, candidates, "resume_subset")
            run.row.status = "finalizing"
            finalizing_checkpoint(run, candidates)
            complete(run, candidates, "Last.fm import completed after resume.")
            return

    username = import_session.source_user_id
    import_session.status = "fetching_lastfm"
    run.log("Fetching Last.fm scrobbles.")
    session.commit()
    run.start("fetching_lastfm")

    def fetched(*, page, total_pages, rows_fetched, total_available):
        if page == 1 or page % 5 == 0 or page == total_pages:
            total = total_available or max(total_pages * 200, rows_fetched)
            run.summary.total_rows = total
            run.progress("Fetching Last.fm scrobbles", rows_fetched, total)
            session.commit()

    result = fetch_lastfm_recent_tracks(
        username or "", api_key, import_events.latest_timestamp(session, repository.user.id, "lastfm", username),
        progress_callback=fetched,
    )
    run.finish_stage()
    rows = result.rows
    run.summary = lastfm_raw_import_summary(rows, [])
    if result.total_available is not None:
        run.summary.total_rows = result.total_available
    run.progress("Storing scrobbles", 0, len(rows))
    run.start("storing_scrobbles")
    run.log("Storing Last.fm scrobbles.", current=0, total=len(rows))
    session.commit()

    def stored(processed, total, persisted):
        if processed == total or processed % 500 == 0:
            run.summary.new_event_rows = persisted
            run.progress("Storing scrobbles", processed, total)
            session.commit()

    raw = persist_lastfm_raw_events(session, repository, import_session, rows, username, stored)
    summary = lastfm_raw_import_summary(rows, raw)
    summary.stage_timings = run.summary.stage_timings
    run.summary = summary
    run.finish_stage()
    run.grouped("Last.fm scrobbles")
    candidates = build_lastfm_candidates_from_rows(
        session, repository, [row for row in raw if row.match_status == "raw_imported"],
        allow_remote_metadata=False, metadata_stats=run.stats, progress_callback=run.matching_progress,
    )
    apply_cached_matches(run, candidates)
    finish_import(run, candidates)


def _username(request: ImportPreviewRequest) -> str:
    if request.source.strip().lower() != "lastfm":
        raise ValueError("Unsupported import source. Only Last.fm imports are enabled.")
    username = (request.lastfm_username or "").strip()
    if not username:
        raise ValueError("Last.fm username is required.")
    return username


def lastfm_api_key() -> str:
    key = get_settings().lastfm_api_key
    if not key:
        raise ValueError("Last.fm imports are temporarily unavailable. Please try again later.")
    return key


def preview_import(
    session: Session, repository: SqliteStateRepository, request: ImportPreviewRequest,
) -> ImportPreviewResponse:
    username = _username(request)
    result = fetch_lastfm_recent_tracks(
        username, lastfm_api_key(), import_events.latest_timestamp(session, repository.user.id, "lastfm", username),
        max_pages=5, max_rows=1000,
    )
    summary = empty_summary()
    summary.total_rows = len(result.rows) if result.total_available is None else result.total_available
    preview, missing, fresh = [], [], []
    for row in result.rows:
        if not row.listened_at or not row.artist:
            summary.failed_rows += 1
            preview.append(ImportPreviewRow(
                **vars(row), status="failed", status_detail="Missing required listened_at or artist value.",
            ))
        elif import_events.has_fingerprint(session, repository.user.id, scrobble_fingerprint(row)):
            summary.duplicate_rows += 1
            preview.append(ImportPreviewRow(
                **vars(row), status="duplicate", status_detail="This scrobble is already stored.", confidence=100,
            ))
        else:
            summary.new_event_rows += 1
            if row.album:
                fresh.append(row)
            else:
                missing.append(ImportPreviewRow(
                    **{**vars(row), "album": None}, status="ignored_missing_album", confidence=10,
                    status_detail="Missing album data. This scrobble will be stored but not reviewed as an album listen.",
                ))
    summary.missing_album_rows = len(missing)
    for events in scrobble_sessions(fresh):
        unique = len({track_identity(event) for event in events} - {""})
        preview.append(ImportPreviewRow(
            listened_at=max(event.listened_at for event in events), artist=events[0].artist, album=events[0].album,
            track=f"{unique}/{unique} tracks matched", source_label="lastfm", status="preview_candidate",
            confidence=min(80, max(25, unique * 10)),
            status_detail=(f"Fast preview candidate with {unique} unique scrobbled tracks. "
                           "Commit import to store scrobbles and run full album-completion matching."),
        ))
        summary.distinct_album_candidates += 1
    preview.extend(missing)
    preview.sort(key=lambda row: row.listened_at or "", reverse=True)
    return ImportPreviewResponse(source=request.source, source_user_id=username, session_name=request.session_name,
                                 columns=[], summary=summary, rows=preview[:100])


def commit_import(
    session: Session, repository: SqliteStateRepository, request: ImportPreviewRequest,
) -> ImportCommitResponse:
    username = _username(request)
    lastfm_api_key()
    row = import_sessions.stage_session(
        session, user_id=repository.user.id, source="lastfm", source_user_id=username, status="queued",
        session_name=request.session_name or f"Last.fm import for {username}", started_at=utc_now(),
        completed_at=None, summary_json=empty_summary().model_dump(),
    )
    append_import_log(session, row, stage="queued", message="Last.fm import queued.")
    session.commit()
    return commit_response(row)


def persist_lastfm_raw_events(session, repository, import_session, rows, username, progress_callback):
    saved = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        if row.listened_at and row.artist:
            fingerprint = scrobble_fingerprint(row)
            if fingerprint not in seen and not import_events.has_fingerprint(session, repository.user.id, fingerprint):
                seen.add(fingerprint)
                values = {**vars(row), "source": "lastfm", "source_user_id": username}
                saved.append(import_events.stage_lastfm_event(
                    session, **values, user_id=repository.user.id, import_session_id=import_session.id,
                    event_fingerprint=fingerprint, match_status="raw_imported" if row.album else "ignored_missing_album",
                    match_confidence=None if row.album else 10,
                    error_message=None if row.album else "Album is missing in the source data.",
                ))
        progress_callback(index, len(rows), len(saved))
    session.flush()
    return saved


def lastfm_raw_import_summary(rows, raw_rows):
    summary = empty_summary()
    summary.total_rows = len(rows)
    summary.new_event_rows = len(raw_rows)
    summary.duplicate_rows = len(rows) - len(raw_rows)
    summary.failed_rows = sum(1 for row in rows if not row.listened_at or not row.artist)
    summary.missing_album_rows = sum(1 for row in raw_rows if not row.album)
    return summary
