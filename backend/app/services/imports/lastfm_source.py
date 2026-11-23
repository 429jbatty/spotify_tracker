"""Preview, queue and store Last.fm scrobbles."""

from typing import Any

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models import ImportSession, ImportedListeningEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories import import_session_repository as import_sessions
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    ImportCommitResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportPreviewSummary,
)
from backend.app.services.import_parsers import NormalizedImportEvent
from backend.app.services.lastfm_import_client import fetch_lastfm_recent_tracks

from .common import utc_now
from .lastfm_candidates import build_lastfm_candidates, scrobble_fingerprint
from .progress import append_import_log, empty_summary, session_summary


LASTFM_PREVIEW_MAX_PAGES = 5
LASTFM_PREVIEW_MAX_SCROBBLES = 1000
LASTFM_IMPORT_UNAVAILABLE_MESSAGE = (
    "Last.fm imports are temporarily unavailable. Please try again later."
)


def preview_import(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportPreviewResponse:
    _validate_source(request)
    source_user_id = _lastfm_username(request)
    fetch_result = fetch_lastfm_recent_tracks(
        source_user_id,
        lastfm_api_key(),
        import_events.latest_timestamp(session, repository.user.id, "lastfm", source_user_id),
        max_pages=LASTFM_PREVIEW_MAX_PAGES,
        max_rows=LASTFM_PREVIEW_MAX_SCROBBLES,
    )
    preview_rows, summary = _lastfm_preview(
        session,
        repository,
        fetch_result.rows,
        source_user_id,
    )
    if fetch_result.total_available is not None:
        summary.total_rows = fetch_result.total_available
    return ImportPreviewResponse(
        source=request.source,
        session_name=request.session_name,
        source_user_id=source_user_id,
        columns=[],
        summary=summary,
        rows=preview_rows[:100],
    )


def lastfm_api_key() -> str:
    api_key = get_settings().lastfm_api_key
    if not api_key:
        raise ValueError(LASTFM_IMPORT_UNAVAILABLE_MESSAGE)
    return api_key


def commit_import(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportCommitResponse:
    _validate_source(request)
    source_user_id = _lastfm_username(request)
    lastfm_api_key()

    import_session = import_sessions.stage_session(
        session,
        user_id=repository.user.id,
        source="lastfm",
        source_user_id=source_user_id,
        status="queued",
        session_name=request.session_name or f"Last.fm import for {source_user_id}",
        started_at=utc_now(),
        completed_at=None,
        summary_json=empty_summary().model_dump(),
    )
    append_import_log(
        session,
        import_session,
        stage="queued",
        message="Last.fm import queued.",
    )
    session.commit()

    summary = session_summary(import_session)
    return ImportCommitResponse(
        import_session_id=import_session.id,
        source="lastfm",
        status=import_session.status,
        session_name=import_session.session_name,
        source_user_id=source_user_id,
        summary=summary,
    )


def _validate_source(request: ImportPreviewRequest) -> None:
    if request.source.strip().lower() != "lastfm":
        raise ValueError("Unsupported import source. Only Last.fm imports are enabled.")


def _lastfm_username(request: ImportPreviewRequest) -> str:
    username = (request.lastfm_username or "").strip()
    if not username:
        raise ValueError("Last.fm username is required.")
    return username


def persist_lastfm_raw_events(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    rows: list[NormalizedImportEvent],
    source_user_id: str | None,
    progress_callback: Any | None = None,
) -> list[ImportedListeningEvent]:
    persisted: list[ImportedListeningEvent] = []
    seen_fingerprints: set[str] = set()
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if not row.listened_at or not row.artist:
            if progress_callback:
                progress_callback(index, total, len(persisted))
            continue
        fingerprint = scrobble_fingerprint(row)
        if fingerprint in seen_fingerprints or import_events.has_fingerprint(session, repository.user.id, fingerprint):
            if progress_callback:
                progress_callback(index, total, len(persisted))
            continue
        seen_fingerprints.add(fingerprint)

        match_status = "raw_imported" if row.album else "ignored_missing_album"
        error_message = None if row.album else "Album is missing in the source data."
        event = import_events.stage_lastfm_event(
            session,
            user_id=repository.user.id,
            import_session_id=import_session.id,
            album_id=None,
            source="lastfm",
            source_user_id=source_user_id,
            source_event_id=row.source_event_id,
            event_fingerprint=fingerprint,
            candidate_key=None,
            listened_at=row.listened_at,
            artist=row.artist,
            album=row.album,
            track=row.track,
            source_label=row.source_label,
            rating=row.rating,
            notes=row.notes,
            match_status=match_status,
            match_confidence=None if row.album else 10,
            error_message=error_message,
            raw_payload=row.raw_payload,
        )
        persisted.append(event)
        if progress_callback:
            progress_callback(index, total, len(persisted))

    session.flush()
    return persisted


def lastfm_raw_import_summary(
    rows: list[NormalizedImportEvent],
    raw_rows: list[ImportedListeningEvent],
) -> ImportPreviewSummary:
    summary = empty_summary()
    summary.total_rows = len(rows)
    summary.new_event_rows = len(raw_rows)
    summary.duplicate_rows = max(0, len(rows) - len(raw_rows))
    summary.failed_rows = sum(1 for row in rows if not row.listened_at or not row.artist)
    summary.missing_album_rows = sum(1 for row in raw_rows if not row.album)
    summary.review_candidates = 0
    summary.unresolved_rows = 0
    return summary


def _lastfm_preview(
    session: Session,
    repository: SqliteStateRepository,
    rows: list[NormalizedImportEvent],
    source_user_id: str | None,
) -> tuple[list[ImportPreviewRow], ImportPreviewSummary]:
    preview_rows: list[ImportPreviewRow] = []
    summary = empty_summary().model_dump()
    summary["total_rows"] = len(rows)

    fresh_rows: list[NormalizedImportEvent] = []
    missing_album_rows: list[NormalizedImportEvent] = []
    for row in rows:
        if not row.listened_at or not row.artist:
            summary["failed_rows"] += 1
            preview_rows.append(
                ImportPreviewRow(
                    listened_at=row.listened_at,
                    artist=row.artist,
                    album=row.album,
                    track=row.track,
                    source_label=row.source_label,
                    rating=row.rating,
                    notes=row.notes,
                    status="failed",
                    status_detail="Missing required listened_at or artist value.",
                    confidence=None,
                )
            )
            continue

        if import_events.has_fingerprint(session, repository.user.id, scrobble_fingerprint(row)):
            summary["duplicate_rows"] += 1
            preview_rows.append(
                ImportPreviewRow(
                    listened_at=row.listened_at,
                    artist=row.artist,
                    album=row.album,
                    track=row.track,
                    source_label=row.source_label,
                    rating=row.rating,
                    notes=row.notes,
                    status="duplicate",
                    status_detail="This scrobble is already stored.",
                    confidence=100,
                )
            )
            continue

        summary["new_event_rows"] += 1
        if not row.album:
            summary["missing_album_rows"] += 1
            missing_album_rows.append(row)
            continue

        fresh_rows.append(row)

    candidates = build_lastfm_candidates(
        session=session,
        repository=repository,
        rows=fresh_rows,
        source_user_id=source_user_id,
        load_metadata=False,
    )

    summary["distinct_album_candidates"] = len(candidates)
    summary["matched_existing_rows"] = sum(
        1 for candidate in candidates if candidate.status == "matched_existing"
    )
    summary["new_album_rows"] = sum(
        1 for candidate in candidates if candidate.status == "new_album"
    )
    summary["derived_album_listens"] = (
        summary["matched_existing_rows"] + summary["new_album_rows"]
    )
    summary["valid_rows"] = summary["derived_album_listens"]
    summary["estimated_new_unique_albums"] = summary["new_album_rows"]
    summary["review_candidates"] = sum(
        1 for candidate in candidates if candidate.status == "candidate_review"
    )
    summary["unresolved_rows"] = summary["review_candidates"]

    for candidate in candidates:
        preview_rows.append(
            ImportPreviewRow(
                listened_at=candidate.listened_at,
                artist=candidate.artist,
                album=candidate.album,
                track=f"{candidate.matched_track_count}/{candidate.total_track_count or candidate.unique_scrobbled_tracks} tracks matched",
                source_label="lastfm",
                rating=None,
                notes=None,
                status=candidate.status,
                status_detail=candidate.status_detail,
                confidence=candidate.confidence,
            )
        )

    for row in missing_album_rows:
        preview_rows.append(
            ImportPreviewRow(
                listened_at=row.listened_at,
                artist=row.artist,
                album=None,
                track=row.track,
                source_label=row.source_label,
                rating=row.rating,
                notes=row.notes,
                status="ignored_missing_album",
                status_detail="Missing album data. This scrobble will be stored but not reviewed as an album listen.",
                confidence=10,
            )
        )

    preview_rows.sort(key=lambda row: row.listened_at or "", reverse=True)
    return preview_rows, ImportPreviewSummary.model_validate(summary)
