import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import album_metadata_service
import metadata_refresh_service
from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.config import get_settings
from backend.app.models import (
    Album,
    AlbumListen,
    AlbumMetadataCache,
    ImportSession,
    ImportedListeningEvent,
    UserAlbum,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    ImportCommitResponse,
    ImportDeleteResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportPreviewSummary,
    ImportResolveRequest,
    ImportReviewItem,
    ImportSessionSummary,
)
from backend.app.services.import_parsers import (
    NormalizedImportEvent,
    clean_text,
)
from backend.app.services.lastfm_import_client import fetch_lastfm_recent_tracks


LASTFM_ALBUM_LISTEN_WINDOW_HOURS = 48
LASTFM_PREVIEW_MAX_PAGES = 5
LASTFM_PREVIEW_MAX_SCROBBLES = 1000
LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS = 3


_ALBUM_METADATA_CACHE_MISS = object()


@dataclass
class LastfmCandidate:
    candidate_key: str
    artist: str
    album: str
    listened_at: str
    events: list[NormalizedImportEvent]
    matched_album_id: int | None
    matched_track_count: int
    total_track_count: int
    unique_scrobbled_tracks: int
    status: str
    status_detail: str
    confidence: int
    metadata: dict[str, Any] | None = None


@dataclass
class ExistingAlbumMatch:
    album_id: int
    record: dict[str, Any]


def _set_import_progress(
    import_session: ImportSession,
    summary: ImportPreviewSummary,
    *,
    label: str,
    current: int,
    total: int,
) -> None:
    summary.progress_label = label
    summary.progress_current = current
    summary.progress_total = total
    import_session.summary_json = summary.model_dump()


def _session_summary(import_session: ImportSession) -> ImportPreviewSummary:
    return ImportPreviewSummary.model_validate(
        import_session.summary_json or _empty_summary().model_dump()
    )


def preview_import(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportPreviewResponse:
    source = request.source.strip().lower()
    if source != "lastfm":
        raise ValueError("Unsupported import source. Only Last.fm imports are enabled.")
    return _preview_lastfm_import(session, repository, request)


def commit_import(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportCommitResponse:
    source = request.source.strip().lower()
    if source != "lastfm":
        raise ValueError("Unsupported import source. Only Last.fm imports are enabled.")
    return _create_lastfm_import_session(session, repository, request)


def run_import_session(session: Session, import_session_id: int) -> ImportSessionSummary:
    import_session = session.get(ImportSession, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")

    repository = SqliteStateRepository(session, user_slug=import_session.user.slug)
    try:
        if import_session.source == "lastfm":
            _run_lastfm_import_session(session, repository, import_session)
        else:
            raise ValueError(f"Unsupported import source: {import_session.source}")
    except Exception:
        summary = _session_summary(import_session)
        import_session.status = "failed"
        import_session.completed_at = _utc_now()
        _set_import_progress(
            import_session,
            summary,
            label="Failed",
            current=summary.progress_current,
            total=summary.progress_total,
        )
        session.commit()
        raise

    return ImportSessionSummary(
        id=import_session.id,
        source=import_session.source,
        source_user_id=import_session.source_user_id,
        status=import_session.status,
        session_name=import_session.session_name,
        started_at=import_session.started_at,
        completed_at=import_session.completed_at,
        summary=_session_summary(import_session),
    )


def import_history(
    session: Session,
    repository: SqliteStateRepository,
) -> list[ImportSessionSummary]:
    rows = session.scalars(
        select(ImportSession)
        .where(ImportSession.user_id == repository.user.id)
        .order_by(ImportSession.started_at.desc(), ImportSession.id.desc())
    ).all()
    return [
        ImportSessionSummary(
            id=row.id,
            source=row.source,
            source_user_id=row.source_user_id,
            status=row.status,
            session_name=row.session_name,
            started_at=row.started_at,
            completed_at=row.completed_at,
            summary=ImportPreviewSummary.model_validate(
                row.summary_json or _empty_summary().model_dump()
            ),
        )
        for row in rows
    ]


def delete_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
) -> ImportDeleteResponse:
    import_session = session.scalars(
        select(ImportSession).where(
            ImportSession.id == import_session_id,
            ImportSession.user_id == repository.user.id,
        )
    ).first()
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")

    imported_rows = session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == repository.user.id,
        )
    ).all()
    album_ids = {row.album_id for row in imported_rows if row.album_id is not None}
    listen_keys = {
        (row.album_id, row.listened_at)
        for row in imported_rows
        if row.album_id is not None and row.listened_at
    }

    deleted_listens = 0
    for album_id, listened_at in listen_keys:
        result = session.execute(
            delete(AlbumListen).where(
                AlbumListen.user_id == repository.user.id,
                AlbumListen.album_id == album_id,
                AlbumListen.listened_at == listened_at,
            )
        )
        deleted_listens += result.rowcount or 0

    deleted_events = len(imported_rows)
    session.execute(
        delete(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == repository.user.id,
        )
    )
    session.delete(import_session)
    session.flush()

    removed_user_albums = 0
    deleted_albums = 0
    for album_id in album_ids:
        user_listen_count = session.scalar(
            select(func.count())
            .select_from(AlbumListen)
            .where(
                AlbumListen.user_id == repository.user.id,
                AlbumListen.album_id == album_id,
            )
        )
        if user_listen_count == 0:
            result = session.execute(
                delete(UserAlbum).where(
                    UserAlbum.user_id == repository.user.id,
                    UserAlbum.album_id == album_id,
                )
            )
            removed_user_albums += result.rowcount or 0

        global_listen_count = session.scalar(
            select(func.count()).select_from(AlbumListen).where(AlbumListen.album_id == album_id)
        )
        global_membership_count = session.scalar(
            select(func.count()).select_from(UserAlbum).where(UserAlbum.album_id == album_id)
        )
        if global_listen_count == 0 and global_membership_count == 0:
            result = session.execute(delete(Album).where(Album.id == album_id))
            deleted_albums += result.rowcount or 0

    session.commit()
    return ImportDeleteResponse(
        import_session_id=import_session_id,
        deleted_events=deleted_events,
        deleted_listens=deleted_listens,
        removed_user_albums=removed_user_albums,
        deleted_albums=deleted_albums,
    )


def unresolved_review_items(
    session: Session,
    repository: SqliteStateRepository,
) -> list[ImportReviewItem]:
    rows = session.scalars(
        select(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.user_id == repository.user.id,
            ImportedListeningEvent.match_status.in_(("candidate_review", "unresolved", "failed")),
        )
        .order_by(ImportedListeningEvent.listened_at.desc(), ImportedListeningEvent.id.desc())
        .limit(1000)
    ).all()

    grouped: dict[tuple[str, str, str, str], ImportedListeningEvent] = {}
    passthrough: list[ImportedListeningEvent] = []
    for row in rows:
        group_key = _review_album_group_key(row)
        if row.match_status == "candidate_review" and group_key:
            current = grouped.get(group_key)
            if current is None or row.listened_at > current.listened_at:
                grouped[group_key] = row
            continue
        passthrough.append(row)

    selected = list(grouped.values()) + passthrough
    selected.sort(key=lambda row: (row.listened_at or "", row.id), reverse=True)

    return [
        ImportReviewItem(
            id=row.id,
            source=row.source,
            source_user_id=row.source_user_id,
            listened_at=row.listened_at,
            artist=row.artist,
            album=row.album,
            track=row.track,
            status=row.match_status,
            status_detail=row.error_message,
            confidence=row.match_confidence,
            session_name=row.import_session.session_name if row.import_session else None,
        )
        for row in selected[:200]
    ]


def resolve_review_item(
    session: Session,
    repository: SqliteStateRepository,
    review_item_id: int,
    request: ImportResolveRequest,
) -> dict[str, Any]:
    review_item = session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.user_id == repository.user.id,
            ImportedListeningEvent.id == review_item_id,
        )
    ).first()
    if review_item is None:
        raise KeyError(f"Import review item not found: {review_item_id}")

    if (request.existing_album_id is None) == (request.create_album is None):
        raise ValueError("Provide either existing_album_id or create_album.")

    target_rows = _review_resolution_target_rows(session, repository, review_item)

    representative_rows = _review_candidate_representatives(target_rows)
    representative = representative_rows[-1]
    if request.existing_album_id is not None:
        album_id = request.existing_album_id
        album = {}
        for target in representative_rows:
            album = repository.add_album_listen(album_id, target.listened_at)
        if representative.rating is not None or representative.notes:
            album = repository.update_user_album_feedback(
                album_id,
                rating=representative.rating,
                notes=representative.notes,
            )
    else:
        create_payload = request.create_album
        created = repository.create_completed_album(
            {
                "artist": create_payload.artist,
                "name": create_payload.name,
                "release_year": create_payload.release_year,
                "release_month": create_payload.release_month,
                "release_day": create_payload.release_day,
                "label": create_payload.label,
                "image_url": create_payload.image_url,
                "spotify_url": create_payload.spotify_url,
                "musicbrainz_url": create_payload.musicbrainz_url,
                "source": representative.source,
                "entry_source": representative.source,
            },
            listen_date=representative.listened_at,
        )
        album_id = created["id"]
        album = created
        for target in representative_rows[:-1]:
            album = repository.add_album_listen(album_id, target.listened_at)
        if representative.rating is not None or representative.notes:
            album = repository.update_user_album_feedback(
                album_id,
                rating=representative.rating,
                notes=representative.notes,
            )

    for row in target_rows:
        row.album_id = album_id
        row.match_status = "resolved"
        row.match_confidence = 100
        row.error_message = None

    session.commit()
    return album


def _review_album_group_key(
    row: ImportedListeningEvent,
) -> tuple[str, str, str, str] | None:
    if not row.artist or not row.album:
        return None
    return (
        row.source or "",
        row.source_user_id or "",
        row.artist.strip().casefold(),
        row.album.strip().casefold(),
    )


def _review_resolution_target_rows(
    session: Session,
    repository: SqliteStateRepository,
    review_item: ImportedListeningEvent,
) -> list[ImportedListeningEvent]:
    group_key = _review_album_group_key(review_item)
    if review_item.match_status == "candidate_review" and group_key:
        candidates = session.scalars(
            select(ImportedListeningEvent).where(
                ImportedListeningEvent.user_id == repository.user.id,
                ImportedListeningEvent.source == review_item.source,
                ImportedListeningEvent.source_user_id == review_item.source_user_id,
                ImportedListeningEvent.match_status == "candidate_review",
            )
        ).all()
        target_rows = [
            row for row in candidates if _review_album_group_key(row) == group_key
        ]
    elif review_item.candidate_key:
        target_rows = session.scalars(
            select(ImportedListeningEvent).where(
                ImportedListeningEvent.user_id == repository.user.id,
                ImportedListeningEvent.candidate_key == review_item.candidate_key,
            )
        ).all()
    else:
        target_rows = [review_item]

    target_rows.sort(key=lambda row: row.listened_at)
    return target_rows


def _review_candidate_representatives(
    rows: list[ImportedListeningEvent],
) -> list[ImportedListeningEvent]:
    grouped: dict[str, ImportedListeningEvent] = {}
    for row in rows:
        key = row.candidate_key or f"row:{row.id}"
        current = grouped.get(key)
        if current is None or row.listened_at > current.listened_at:
            grouped[key] = row

    representatives = list(grouped.values())
    representatives.sort(key=lambda row: row.listened_at)
    return representatives


def _preview_lastfm_import(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportPreviewResponse:
    rows, _, source_user_id, total_available = _parse_lastfm(
        session,
        repository,
        request,
        max_pages=LASTFM_PREVIEW_MAX_PAGES,
        max_rows=LASTFM_PREVIEW_MAX_SCROBBLES,
    )
    preview_rows, summary = _lastfm_preview(
        session,
        repository,
        rows,
        source_user_id,
        load_metadata=False,
    )
    if total_available is not None:
        summary.total_rows = total_available
    return ImportPreviewResponse(
        source=request.source,
        session_name=request.session_name,
        source_user_id=source_user_id,
        columns=[],
        summary=summary,
        rows=preview_rows[:100],
    )


def _create_lastfm_import_session(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
) -> ImportCommitResponse:
    source_user_id = _lastfm_username(request)
    settings = get_settings()
    if not settings.lastfm_api_key:
        raise ValueError("LASTFM_API_KEY is not configured.")

    import_session = ImportSession(
        user_id=repository.user.id,
        source="lastfm",
        source_user_id=source_user_id,
        status="queued",
        session_name=request.session_name or _default_session_name(request, source_user_id),
        started_at=_utc_now(),
        completed_at=None,
        summary_json=_empty_summary().model_dump(),
    )
    session.add(import_session)
    session.commit()

    summary = _session_summary(import_session)
    return ImportCommitResponse(
        import_session_id=import_session.id,
        source="lastfm",
        status=import_session.status,
        session_name=import_session.session_name,
        source_user_id=source_user_id,
        summary=summary,
    )


def _run_lastfm_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    source_user_id = import_session.source_user_id
    settings = get_settings()
    if not settings.lastfm_api_key:
        raise ValueError("LASTFM_API_KEY is not configured.")

    import_session.status = "fetching_lastfm"
    session.commit()

    fetch_summary = _empty_summary()

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
        _set_import_progress(
            import_session,
            fetch_summary,
            label="Fetching Last.fm scrobbles",
            current=rows_fetched,
            total=total,
        )
        session.commit()

    fetch_result = fetch_lastfm_recent_tracks(
        source_user_id or "",
        settings.lastfm_api_key,
        latest_imported_timestamp(
            session,
            repository.user.id,
            "lastfm",
            source_user_id=source_user_id,
        ),
        progress_callback=update_fetch_progress,
    )

    rows = fetch_result.rows
    summary = _lastfm_raw_import_summary(rows, [])
    if fetch_result.total_available is not None:
        summary.total_rows = fetch_result.total_available
    _set_import_progress(
        import_session,
        summary,
        label="Storing scrobbles",
        current=0,
        total=len(rows),
    )
    import_session.status = "storing_scrobbles"
    session.commit()

    def update_store_progress(processed: int, total: int, persisted: int) -> None:
        if processed != total and processed % 500 != 0:
            return
        summary.new_event_rows = persisted
        _set_import_progress(
            import_session,
            summary,
            label="Storing scrobbles",
            current=processed,
            total=total,
        )
        session.commit()

    raw_rows = _persist_lastfm_raw_events(
        session=session,
        repository=repository,
        import_session=import_session,
        rows=rows,
        source_user_id=source_user_id,
        progress_callback=update_store_progress,
    )
    summary = _lastfm_raw_import_summary(rows, raw_rows)
    import_session.status = "grouping_album_sessions"
    _set_import_progress(
        import_session,
        summary,
        label="Grouping album sessions",
        current=0,
        total=0,
    )
    session.commit()

    candidate_rows = [row for row in raw_rows if row.match_status == "raw_imported"]

    import_session.status = "matching_cached_albums"

    def update_cached_match_progress(
        current: int,
        total: int,
        partial_candidates: list[LastfmCandidate],
    ) -> None:
        _apply_lastfm_candidate_summary(summary, partial_candidates)
        _set_import_progress(
            import_session,
            summary,
            label="Matching cached albums",
            current=current,
            total=total,
        )
        session.commit()

    cached_candidates = _build_lastfm_candidates_from_imported_events(
        repository=repository,
        imported_rows=candidate_rows,
        allow_remote_metadata=False,
        progress_callback=update_cached_match_progress,
    )
    _apply_lastfm_candidate_summary(summary, cached_candidates)
    session.flush()
    _process_lastfm_candidates(
        session=session,
        repository=repository,
        candidates=cached_candidates,
    )
    session.commit()

    pending_rows = session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == repository.user.id,
            ImportedListeningEvent.match_status == "pending_metadata",
        )
    ).all()

    if pending_rows:
        import_session.status = "fetching_metadata"
        _set_import_progress(
            import_session,
            summary,
            label="Fetching MusicBrainz metadata",
            current=0,
            total=len({row.candidate_key for row in pending_rows if row.candidate_key}),
        )
        session.commit()

        def update_remote_match_progress(
            current: int,
            total: int,
            remote_candidates: list[LastfmCandidate],
        ) -> None:
            combined_candidates = [
                candidate
                for candidate in cached_candidates
                if candidate.status not in {"no_tracklist", "pending_metadata"}
            ] + remote_candidates
            _apply_lastfm_candidate_summary(summary, combined_candidates)
            _set_import_progress(
                import_session,
                summary,
                label="Fetching MusicBrainz metadata",
                current=current,
                total=total,
            )
            session.commit()

        remote_candidates = _build_lastfm_candidates_from_imported_events(
            repository=repository,
            imported_rows=pending_rows,
            allow_remote_metadata=True,
            progress_callback=update_remote_match_progress,
        )
        final_candidates = [
            candidate
            for candidate in cached_candidates
            if candidate.status not in {"no_tracklist", "pending_metadata"}
        ] + remote_candidates
        _apply_lastfm_candidate_summary(summary, final_candidates)
        session.flush()
        _process_lastfm_candidates(
            session=session,
            repository=repository,
            candidates=remote_candidates,
        )
        session.commit()
    else:
        final_candidates = cached_candidates

    import_session.status = "finalizing"
    _set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    session.commit()

    _apply_lastfm_candidate_summary(summary, final_candidates)
    import_session.status = "completed"
    import_session.completed_at = _utc_now()
    _set_import_progress(
        import_session,
        summary,
        label="Completed",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    import_session.summary_json = summary.model_dump()
    session.commit()


def _parse_lastfm(
    session: Session,
    repository: SqliteStateRepository,
    request: ImportPreviewRequest,
    *,
    max_pages: int | None = None,
    max_rows: int | None = None,
) -> tuple[
    list[NormalizedImportEvent],
    list[str],
    str | None,
    int | None,
]:
    username = _lastfm_username(request)

    settings = get_settings()
    if not settings.lastfm_api_key:
        raise ValueError("LASTFM_API_KEY is not configured.")

    fetch_result = fetch_lastfm_recent_tracks(
        username,
        settings.lastfm_api_key,
        latest_imported_timestamp(
            session,
            repository.user.id,
            "lastfm",
            source_user_id=username,
        ),
        max_pages=max_pages,
        max_rows=max_rows,
    )
    return fetch_result.rows, [], username, fetch_result.total_available


def _lastfm_username(request: ImportPreviewRequest) -> str:
    username = (request.lastfm_username or "").strip()
    if not username:
        raise ValueError("Last.fm username is required.")
    return username


def _persist_lastfm_raw_events(
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
        fingerprint = _fingerprint(row)
        if fingerprint in seen_fingerprints or _event_exists(session, repository.user.id, row):
            if progress_callback:
                progress_callback(index, total, len(persisted))
            continue
        seen_fingerprints.add(fingerprint)

        match_status = "raw_imported" if row.album else "ignored_missing_album"
        error_message = None if row.album else "Album is missing in the source data."
        event = ImportedListeningEvent(
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
        session.add(event)
        persisted.append(event)
        if progress_callback:
            progress_callback(index, total, len(persisted))

    session.flush()
    return persisted


def _process_lastfm_candidates(
    session: Session,
    repository: SqliteStateRepository,
    candidates: list[LastfmCandidate],
) -> None:
    album_index = _existing_album_index(repository)
    for candidate in candidates:
        candidate_rows = session.scalars(
            select(ImportedListeningEvent).where(
                ImportedListeningEvent.user_id == repository.user.id,
                ImportedListeningEvent.candidate_key == candidate.candidate_key,
            )
        ).all()
        if not candidate_rows:
            continue

        album_id = candidate.matched_album_id
        status = candidate.status
        error_message = candidate.status_detail

        if candidate.status == "matched_existing" and album_id is not None:
            repository.add_album_listen(album_id, candidate.listened_at)
        elif candidate.status == "new_album":
            record = candidate.metadata or _build_album_record(candidate.events[-1])
            album_key = _album_match_key(record.get("artist"), record.get("name"))
            existing_album = album_index.get(album_key)
            if existing_album is not None:
                repository.add_album_listen(existing_album.album_id, candidate.listened_at)
                album_id = existing_album.album_id
            else:
                created = repository.create_completed_album(
                    record,
                    listen_date=candidate.listened_at,
                )
                album_id = created["id"]
                album_index[album_key] = ExistingAlbumMatch(album_id=album_id, record=created)
        else:
            album_id = None

        if status in {"matched_existing", "new_album"}:
            persisted_status = "processed_album_listen"
        elif status == "candidate_review":
            persisted_status = "candidate_review"
        elif status in {"no_tracklist", "pending_metadata"}:
            persisted_status = "pending_metadata"
        else:
            persisted_status = status

        for row in candidate_rows:
            row.album_id = album_id
            row.match_status = persisted_status
            row.match_confidence = candidate.confidence
            row.error_message = error_message


def _lastfm_raw_import_summary(
    rows: list[NormalizedImportEvent],
    raw_rows: list[ImportedListeningEvent],
) -> ImportPreviewSummary:
    summary = _empty_summary()
    summary.total_rows = len(rows)
    summary.new_event_rows = len(raw_rows)
    summary.duplicate_rows = max(0, len(rows) - len(raw_rows))
    summary.failed_rows = sum(1 for row in rows if not row.listened_at or not row.artist)
    summary.missing_album_rows = sum(1 for row in raw_rows if not row.album)
    summary.review_candidates = 0
    summary.unresolved_rows = 0
    return summary


def _apply_lastfm_candidate_summary(
    summary: ImportPreviewSummary,
    candidates: list[LastfmCandidate],
) -> None:
    summary.distinct_album_candidates = len(candidates)
    summary.matched_existing_rows = sum(
        1 for candidate in candidates if candidate.status == "matched_existing"
    )
    summary.new_album_rows = sum(1 for candidate in candidates if candidate.status == "new_album")
    summary.derived_album_listens = summary.matched_existing_rows + summary.new_album_rows
    summary.valid_rows = summary.derived_album_listens
    summary.estimated_new_unique_albums = summary.new_album_rows
    summary.review_candidates = sum(
        1 for candidate in candidates if candidate.status == "candidate_review"
    )
    summary.unresolved_rows = summary.review_candidates
    summary.pending_metadata_candidates = sum(
        1 for candidate in candidates if candidate.status in {"no_tracklist", "pending_metadata"}
    )


def _lastfm_preview(
    session: Session,
    repository: SqliteStateRepository,
    rows: list[NormalizedImportEvent],
    source_user_id: str | None,
    *,
    load_metadata: bool = True,
) -> tuple[list[ImportPreviewRow], ImportPreviewSummary]:
    preview_rows: list[ImportPreviewRow] = []
    summary = _empty_summary().model_dump()
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

        if _event_exists(session, repository.user.id, row):
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

    candidates = _build_lastfm_candidates_from_events(
        repository=repository,
        rows=fresh_rows,
        source_user_id=source_user_id,
        load_metadata=load_metadata,
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


def _build_lastfm_candidates_from_imported_events(
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    allow_remote_metadata: bool = True,
    progress_callback: Any | None = None,
) -> list[LastfmCandidate]:
    events = [
        NormalizedImportEvent(
            listened_at=row.listened_at,
            artist=row.artist,
            album=row.album,
            track=row.track,
            source=row.source,
            source_user_id=row.source_user_id,
            source_event_id=row.source_event_id,
            source_label=row.source_label,
            rating=row.rating,
            notes=row.notes,
            raw_payload=row.raw_payload or {},
        )
        for row in imported_rows
    ]
    candidates = _build_lastfm_candidates_from_events(
        repository=repository,
        rows=events,
        source_user_id=imported_rows[0].source_user_id if imported_rows else None,
        load_metadata=True,
        allow_remote_metadata=allow_remote_metadata,
        progress_callback=progress_callback,
    )
    imported_lookup = {
        _fingerprint(event): row
        for event, row in zip(events, imported_rows)
    }
    for candidate in candidates:
        for event in candidate.events:
            imported_row = imported_lookup.get(_fingerprint(event))
            if imported_row is not None:
                imported_row.candidate_key = candidate.candidate_key
    return candidates


def _build_lastfm_candidates_from_events(
    repository: SqliteStateRepository,
    rows: list[NormalizedImportEvent],
    source_user_id: str | None,
    *,
    load_metadata: bool = True,
    allow_remote_metadata: bool = True,
    progress_callback: Any | None = None,
) -> list[LastfmCandidate]:
    grouped: dict[tuple[str, str], list[NormalizedImportEvent]] = defaultdict(list)
    for row in rows:
        if not row.artist or not row.album or not row.listened_at:
            continue
        grouped[(row.artist.casefold(), row.album.casefold())].append(row)

    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = _existing_album_index(repository)
    candidate_event_chunks: list[list[NormalizedImportEvent]] = []
    for event_group in grouped.values():
        event_group.sort(key=lambda row: _parse_timestamp(row.listened_at))
        candidate_event_chunks.extend(_split_lastfm_sessions(event_group))

    candidates: list[LastfmCandidate] = []
    total_candidates = len(candidate_event_chunks)
    for index, chunk in enumerate(candidate_event_chunks, start=1):
        candidate = _build_lastfm_candidate(
            repository=repository,
            events=chunk,
            source_user_id=source_user_id,
            metadata_cache=metadata_cache,
            existing_album_index=existing_album_index,
            load_metadata=load_metadata,
            allow_remote_metadata=allow_remote_metadata,
        )
        candidates.append(candidate)
        if progress_callback and (index == 1 or index % 5 == 0 or index == total_candidates):
            progress_callback(index, total_candidates, candidates)
    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    return candidates


def _build_lastfm_candidate(
    repository: SqliteStateRepository,
    events: list[NormalizedImportEvent],
    source_user_id: str | None,
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None],
    existing_album_index: dict[tuple[str, str], ExistingAlbumMatch],
    *,
    load_metadata: bool = True,
    allow_remote_metadata: bool = True,
) -> LastfmCandidate:
    artist = events[0].artist or "Unknown Artist"
    album = events[0].album or "Unknown Album"
    listened_at = max(event.listened_at for event in events if event.listened_at)
    matched_album = existing_album_index.get(_album_match_key(artist, album))
    matched_album_id = matched_album.album_id if matched_album else None
    unique_tracks = {
        _normalize_track_name(event.track)
        for event in events
        if _normalize_track_name(event.track)
    }
    remote_metadata_allowed = (
        allow_remote_metadata
        and len(unique_tracks) >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS
    )
    metadata = (
        _lastfm_album_metadata(
            repository.session,
            artist,
            album,
            metadata_cache,
            matched_album_id=matched_album_id,
            matched_album_record=matched_album.record if matched_album else None,
            allow_remote_metadata=remote_metadata_allowed,
        )
        if load_metadata
        else None
    )

    matched_track_count = 0
    total_track_count = 0
    confidence = 25
    status = "partial_listen"
    if not load_metadata:
        matched_track_count = len(unique_tracks)
        confidence = min(80, max(25, matched_track_count * 10))
        status = "preview_candidate"
        detail = (
            f"Fast preview candidate with {matched_track_count} unique scrobbled tracks. "
            "Commit import to store scrobbles and run full album-completion matching."
        )
    elif metadata and metadata.get("tracklist"):
        metadata_tracks = {
            _normalize_track_name(track.get("title"))
            for track in metadata.get("tracklist") or []
            if _normalize_track_name(track.get("title"))
        }
        total_track_count = len(metadata_tracks)
        matched_track_count = len(unique_tracks & metadata_tracks)
        if total_track_count > 0:
            confidence = round((matched_track_count / total_track_count) * 100)
        if matched_album_id is None and not _is_lastfm_importable_album_metadata(
            metadata,
            total_track_count,
        ):
            status = "partial_listen"
            detail = (
                "MusicBrainz matched this to a single or short non-album release, "
                "so it does not count as a completed album listen."
            )
        elif total_track_count > 0 and (matched_track_count / total_track_count) >= ALBUM_COMPLETION_THRESHOLD:
            status = "matched_existing" if matched_album_id is not None else "new_album"
            detail = (
                f"Matched {matched_track_count} of {total_track_count} tracks. "
                "This will count as a completed album listen."
            )
        else:
            status = "partial_listen"
            detail = (
                f"Matched {matched_track_count} of {total_track_count or len(unique_tracks)} tracks. "
                "This does not count as a completed album listen."
            )
    elif len(unique_tracks) < LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS:
        status = "partial_listen"
        detail = (
            f"Only {len(unique_tracks)} unique tracks were scrobbled; skipped remote metadata "
            "lookup because this is not enough evidence for a full album listen."
        )
    elif not allow_remote_metadata:
        status = "no_tracklist"
        detail = (
            "No local or cached tracklist is available yet, so this scrobble session "
            "does not count as a completed album listen."
        )
    else:
        status = "candidate_review"
        detail = "Could not load album tracklist, so this scrobble session needs review."

    candidate_key = _lastfm_candidate_key(source_user_id, artist, album, events)
    return LastfmCandidate(
        candidate_key=candidate_key,
        artist=artist,
        album=album,
        listened_at=listened_at,
        events=events,
        matched_album_id=matched_album_id,
        matched_track_count=matched_track_count,
        total_track_count=total_track_count,
        unique_scrobbled_tracks=len(unique_tracks),
        status=status,
        status_detail=detail,
        confidence=confidence,
        metadata=metadata,
    )


def _is_lastfm_importable_album_metadata(
    metadata: dict[str, Any],
    total_track_count: int,
) -> bool:
    primary_type = (metadata.get("primary_type") or "").strip().casefold()
    if primary_type:
        return primary_type == "album"

    return total_track_count >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS


def _split_lastfm_sessions(
    rows: list[NormalizedImportEvent],
) -> list[list[NormalizedImportEvent]]:
    sessions: list[list[NormalizedImportEvent]] = []
    current: list[NormalizedImportEvent] = []
    session_start_dt: datetime | None = None
    previous_dt: datetime | None = None
    listen_window = timedelta(hours=LASTFM_ALBUM_LISTEN_WINDOW_HOURS)

    for row in rows:
        current_dt = _parse_timestamp(row.listened_at)
        if not current or previous_dt is None:
            current = [row]
            session_start_dt = current_dt
            previous_dt = current_dt
            continue

        if session_start_dt is not None and current_dt - session_start_dt > listen_window:
            sessions.append(current)
            current = [row]
            session_start_dt = current_dt
        else:
            current.append(row)
        previous_dt = current_dt

    if current:
        sessions.append(current)
    return sessions


def _lastfm_album_metadata(
    session: Session,
    artist: str,
    album: str,
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None],
    *,
    matched_album_id: int | None,
    matched_album_record: dict[str, Any] | None,
    allow_remote_metadata: bool = True,
) -> dict[str, Any] | None:
    cache_key = (artist.casefold(), album.casefold())
    if cache_key in metadata_cache:
        return metadata_cache[cache_key]

    if matched_album_id is not None and matched_album_record and matched_album_record.get("tracklist"):
        metadata_cache[cache_key] = matched_album_record
        return matched_album_record

    cached = _read_album_metadata_cache(session, artist, album)
    if cached is not _ALBUM_METADATA_CACHE_MISS:
        metadata_cache[cache_key] = cached if isinstance(cached, dict) else None
        return metadata_cache[cache_key]

    if not allow_remote_metadata:
        metadata_cache[cache_key] = None
        return None

    try:
        metadata = album_metadata_service.get_album_metadata_for_import_matching(artist, album)
        if metadata:
            metadata["entry_source"] = "lastfm"
            metadata.pop("_refresh_warnings", None)
    except Exception:
        metadata_cache[cache_key] = None
        return None

    _write_album_metadata_cache(session, artist, album, metadata)
    metadata_cache[cache_key] = metadata
    return metadata


def _album_match_key(artist: str | None, album: str | None) -> tuple[str, str]:
    return ((artist or "").strip().casefold(), (album or "").strip().casefold())


def _existing_album_index(
    repository: SqliteStateRepository,
) -> dict[tuple[str, str], ExistingAlbumMatch]:
    rows = repository.session.scalars(
        select(Album)
        .join(UserAlbum)
        .where(UserAlbum.user_id == repository.user.id)
    ).all()
    index: dict[tuple[str, str], ExistingAlbumMatch] = {}
    for album in rows:
        record = repository.get_completed_album_record_by_id(album.id)
        index[_album_match_key(album.artist, album.name)] = ExistingAlbumMatch(
            album_id=album.id,
            record=record,
        )
    return index


def _album_metadata_cache_key(artist: str, album: str) -> str:
    return hashlib.sha256(
        "|".join(["musicbrainz-import", artist.strip().casefold(), album.strip().casefold()]).encode(
            "utf-8"
        )
    ).hexdigest()


def _read_album_metadata_cache(
    session: Session,
    artist: str,
    album: str,
) -> dict[str, Any] | None | object:
    row = session.scalars(
        select(AlbumMetadataCache).where(
            AlbumMetadataCache.cache_key == _album_metadata_cache_key(artist, album)
        )
    ).first()
    if row is None:
        return _ALBUM_METADATA_CACHE_MISS
    return row.metadata_json if row.status == "matched" else None


def _write_album_metadata_cache(
    session: Session,
    artist: str,
    album: str,
    metadata: dict[str, Any] | None,
) -> None:
    cache_key = _album_metadata_cache_key(artist, album)
    row = session.scalars(
        select(AlbumMetadataCache).where(AlbumMetadataCache.cache_key == cache_key)
    ).first()
    if row is None:
        row = AlbumMetadataCache(cache_key=cache_key, artist=artist, album=album)
        session.add(row)

    row.status = "matched" if metadata else "not_found"
    row.metadata_json = metadata or {}
    row.error_message = None if metadata else "No import matching metadata found."
    row.updated_at = _utc_now()
    session.flush()


def _lastfm_candidate_key(
    source_user_id: str | None,
    artist: str,
    album: str,
    events: list[NormalizedImportEvent],
) -> str:
    payload = "|".join(
        [
            "lastfm",
            source_user_id or "",
            artist.casefold(),
            album.casefold(),
            events[0].listened_at or "",
            events[-1].listened_at or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _empty_summary() -> ImportPreviewSummary:
    return ImportPreviewSummary(
        total_rows=0,
        new_event_rows=0,
        valid_rows=0,
        duplicate_rows=0,
        unresolved_rows=0,
        failed_rows=0,
        matched_existing_rows=0,
        new_album_rows=0,
        missing_album_rows=0,
        distinct_album_candidates=0,
        estimated_new_unique_albums=0,
        derived_album_listens=0,
        review_candidates=0,
        pending_metadata_candidates=0,
        progress_current=0,
        progress_total=0,
        progress_label=None,
    )


def _default_session_name(request: ImportPreviewRequest, source_user_id: str | None) -> str:
    if source_user_id:
        return f"Last.fm import for {source_user_id}"
    return "Last.fm import"


def _build_album_record(event: NormalizedImportEvent) -> dict[str, Any]:
    record = {
        "artist": event.artist,
        "name": event.album,
        "source": "musicbrainz" if event.source == "lastfm" else event.source,
        "entry_source": event.source,
    }
    if event.notes:
        record["notes"] = event.notes

    try:
        refreshed = metadata_refresh_service.refresh_album_record(record)
        refreshed.pop("_refresh_warnings", None)
        if not _metadata_matches_imported_album(event, refreshed):
            return record
        return refreshed
    except Exception:
        return record


def _metadata_matches_imported_album(
    event: NormalizedImportEvent,
    metadata: dict[str, Any],
) -> bool:
    imported_artist = clean_text(event.artist)
    imported_album = clean_text(event.album)
    metadata_artist = clean_text(metadata.get("artist"))
    metadata_album = clean_text(metadata.get("name"))
    if not imported_artist or not imported_album or not metadata_artist or not metadata_album:
        return False

    artist_score = fuzz.token_set_ratio(imported_artist.casefold(), metadata_artist.casefold())
    album_score = fuzz.token_set_ratio(imported_album.casefold(), metadata_album.casefold())
    return artist_score >= 85 and album_score >= 85


def latest_imported_timestamp(
    session: Session,
    user_id: int,
    source: str,
    source_user_id: str | None = None,
) -> str | None:
    query = select(func.max(ImportedListeningEvent.listened_at)).where(
        ImportedListeningEvent.user_id == user_id,
        ImportedListeningEvent.source == source,
    )
    if source_user_id:
        query = query.where(ImportedListeningEvent.source_user_id == source_user_id)
    return session.scalar(query)


def _event_exists(session: Session, user_id: int, row: NormalizedImportEvent) -> bool:
    return (
        session.scalars(
            select(ImportedListeningEvent.id).where(
                ImportedListeningEvent.user_id == user_id,
                ImportedListeningEvent.event_fingerprint == _fingerprint(row),
            )
        ).first()
        is not None
    )


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_track_name(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _fingerprint(event: NormalizedImportEvent) -> str:
    payload = "|".join(
        [
            event.listened_at or "",
            (event.artist or "").casefold(),
            (event.album or "").casefold(),
            (event.track or "").casefold(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
