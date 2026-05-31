import hashlib
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
    ImportSessionLog,
    ImportedListeningEvent,
    SpotifyStreamingEvent,
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
    ImportProgressStep,
    ImportSessionLogEntry,
    ImportSessionSummary,
)
from backend.app.services.import_parsers import (
    NormalizedImportEvent,
    clean_text,
)
from backend.app.services.lastfm_import_client import fetch_lastfm_recent_tracks
from backend.app.services.spotify_import_parser import (
    iter_spotify_history_events,
    spotify_history_entries_from_zip,
    spotify_streaming_fingerprint,
)


LASTFM_ALBUM_LISTEN_WINDOW_HOURS = 48
LASTFM_PREVIEW_MAX_PAGES = 5
LASTFM_PREVIEW_MAX_SCROBBLES = 1000
LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS = 3
SPOTIFY_IMPORT_SOURCE = "spotify_import"
SPOTIFY_IMPORT_INSERT_BATCH_SIZE = 2_000
SPOTIFY_REMOTE_METADATA_MIN_UNIQUE_TRACKS = 5
SPOTIFY_REMOTE_METADATA_MIN_MS_PLAYED = 20 * 60 * 1000
SPOTIFY_REMOTE_METADATA_ALWAYS_UNIQUE_TRACKS = 8
TERMINAL_IMPORT_STATUSES = {"completed", "failed"}
RESUMABLE_IMPORT_STATUSES = {
    "queued",
    "validating_zip",
    "parsing_spotify_history",
    "storing_streaming_events",
    "fetching_lastfm",
    "storing_scrobbles",
    "grouping_album_sessions",
    "matching_cached_albums",
    "fetching_metadata",
    "finalizing",
}
IMPORT_STEP_ORDER = [
    ("store_source", "Store source data"),
    ("find_sessions", "Find album sessions"),
    ("check_saved", "Check saved metadata"),
    ("lookup_missing", "Look up missing albums"),
    ("finalize", "Finalize"),
]
STATUS_TO_STEP = {
    "queued": "store_source",
    "validating_zip": "store_source",
    "parsing_spotify_history": "store_source",
    "storing_streaming_events": "store_source",
    "fetching_lastfm": "store_source",
    "storing_scrobbles": "store_source",
    "grouping_album_sessions": "find_sessions",
    "matching_cached_albums": "check_saved",
    "fetching_metadata": "lookup_missing",
    "finalizing": "finalize",
    "completed": "finalize",
    "failed": "finalize",
}


_ALBUM_METADATA_CACHE_MISS = object()
logger = logging.getLogger(__name__)


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


@dataclass
class ImportMetadataStats:
    cache_hits: int = 0
    cache_misses: int = 0
    lookup_seconds: list[float] = None

    def __post_init__(self) -> None:
        if self.lookup_seconds is None:
            self.lookup_seconds = []

    @property
    def request_count(self) -> int:
        return len(self.lookup_seconds)

    @property
    def average_seconds(self) -> float | None:
        if not self.lookup_seconds:
            return None
        return sum(self.lookup_seconds) / len(self.lookup_seconds)

    @property
    def p95_seconds(self) -> float | None:
        if not self.lookup_seconds:
            return None
        ordered = sorted(self.lookup_seconds)
        index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
        return ordered[index]


@dataclass
class ImportStageTimer:
    import_session_id: int
    summary: ImportPreviewSummary
    active_stage: str | None = None
    active_started_at: float | None = None

    def start(self, stage: str) -> None:
        self.finish()
        self.active_stage = stage
        self.active_started_at = time.perf_counter()
        logger.info("import_session=%s stage=%s started", self.import_session_id, stage)

    def finish(self) -> None:
        if self.active_stage is None or self.active_started_at is None:
            return
        elapsed = time.perf_counter() - self.active_started_at
        timings = dict(self.summary.stage_timings or {})
        timings[self.active_stage] = round(timings.get(self.active_stage, 0.0) + elapsed, 3)
        self.summary.stage_timings = timings
        logger.info(
            "import_session=%s stage=%s completed elapsed_s=%.3f",
            self.import_session_id,
            self.active_stage,
            elapsed,
        )
        self.active_stage = None
        self.active_started_at = None


def _append_import_log(
    session: Session,
    import_session: ImportSession,
    *,
    message: str,
    level: str = "info",
    stage: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    current: int | None = None,
    total: int | None = None,
    elapsed_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        ImportSessionLog(
            import_session_id=import_session.id,
            created_at=_utc_now(),
            level=level,
            stage=stage,
            message=message,
            artist=artist,
            album=album,
            current=current,
            total=total,
            elapsed_seconds=elapsed_seconds,
            metadata_json=metadata or {},
        )
    )
    logger.info(
        "import_session=%s stage=%s level=%s message=%s",
        import_session.id,
        stage,
        level,
        message,
    )


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


def _apply_metadata_stats(
    summary: ImportPreviewSummary,
    stats: ImportMetadataStats,
    *,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if current is not None:
        summary.metadata_lookup_current = current
    if total is not None:
        summary.metadata_lookup_total = total
    summary.metadata_cache_hits = stats.cache_hits
    summary.metadata_cache_misses = stats.cache_misses
    summary.musicbrainz_requests = stats.request_count
    summary.musicbrainz_lookup_seconds_avg = (
        round(stats.average_seconds, 3) if stats.average_seconds is not None else None
    )
    summary.musicbrainz_lookup_seconds_p95 = (
        round(stats.p95_seconds, 3) if stats.p95_seconds is not None else None
    )
    if (
        current is not None
        and total is not None
        and current > 0
        and total > current
        and stats.average_seconds is not None
    ):
        summary.estimated_seconds_remaining = round((total - current) * stats.average_seconds, 3)
    elif current is not None and total is not None and current >= total:
        summary.estimated_seconds_remaining = 0


def _session_summary(import_session: ImportSession) -> ImportPreviewSummary:
    return ImportPreviewSummary.model_validate(
        import_session.summary_json or _empty_summary().model_dump()
    )


def _build_progress_steps(
    import_session: ImportSession,
    summary: ImportPreviewSummary,
) -> list[ImportProgressStep]:
    current_key = STATUS_TO_STEP.get(import_session.status)
    current_index = next(
        (index for index, (key, _) in enumerate(IMPORT_STEP_ORDER) if key == current_key),
        len(IMPORT_STEP_ORDER) - 1,
    )
    steps: list[ImportProgressStep] = []
    for index, (key, label) in enumerate(IMPORT_STEP_ORDER):
        if import_session.status == "failed" and key == current_key:
            status = "failed"
        elif import_session.status == "completed" or index < current_index:
            status = "completed"
        elif index == current_index and import_session.status not in TERMINAL_IMPORT_STATUSES:
            status = "current"
        else:
            status = "pending"

        current = 0
        total = 0
        detail = None
        if key == current_key:
            current = summary.progress_current
            total = summary.progress_total
            detail = _current_step_detail(import_session, summary)
        elif key == "store_source":
            current = summary.new_event_rows
            total = summary.total_rows
        elif key == "find_sessions":
            current = summary.distinct_album_candidates
            total = summary.distinct_album_candidates
        elif key == "lookup_missing":
            current = summary.metadata_lookup_current
            total = summary.metadata_lookup_total

        steps.append(
            ImportProgressStep(
                key=key,
                label=label,
                status=status,
                current=current,
                total=total,
                detail=detail,
            )
        )
    return steps


def _current_step_detail(
    import_session: ImportSession,
    summary: ImportPreviewSummary,
) -> str | None:
    if import_session.status == "completed":
        return "Import complete."
    if import_session.status == "failed":
        return summary.progress_label or "Import failed."
    if import_session.status in {"validating_zip", "queued"}:
        return "Preparing the import."
    if import_session.status in {"parsing_spotify_history", "storing_streaming_events"}:
        return f"{summary.progress_current:,} of {summary.progress_total:,} Spotify plays stored."
    if import_session.status in {"fetching_lastfm", "storing_scrobbles"}:
        return f"{summary.progress_current:,} of {summary.progress_total:,} Last.fm scrobbles stored."
    if import_session.status == "matching_cached_albums":
        return f"{summary.progress_current:,} of {summary.progress_total:,} album sessions checked locally."
    if import_session.status == "fetching_metadata":
        total = summary.metadata_lookup_total or summary.progress_total
        current = summary.metadata_lookup_current or summary.progress_current
        return f"{current:,} of {total:,} unique albums checked with MusicBrainz."
    if import_session.status == "finalizing":
        return "Writing final import results."
    return summary.progress_label


def _build_import_session_summary(import_session: ImportSession) -> ImportSessionSummary:
    summary = _session_summary(import_session)
    steps = _build_progress_steps(import_session, summary)
    current_key = STATUS_TO_STEP.get(import_session.status)
    current_step = next((step for step in steps if step.key == current_key), None)
    elapsed_seconds = None
    try:
        started = _parse_timestamp(import_session.started_at)
        ended = _parse_timestamp(import_session.completed_at) if import_session.completed_at else datetime.now(timezone.utc)
        elapsed_seconds = round((ended - started).total_seconds(), 3)
    except Exception:
        elapsed_seconds = None
    return ImportSessionSummary(
        id=import_session.id,
        source=import_session.source,
        source_user_id=import_session.source_user_id,
        status=import_session.status,
        session_name=import_session.session_name,
        started_at=import_session.started_at,
        completed_at=import_session.completed_at,
        summary=summary,
        steps=steps,
        current_step_key=current_step.key if current_step else None,
        current_step_label=current_step.label if current_step else None,
        current_step_detail=current_step.detail if current_step else None,
        elapsed_seconds=elapsed_seconds,
        estimated_seconds_remaining=summary.estimated_seconds_remaining,
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
        elif import_session.source == SPOTIFY_IMPORT_SOURCE:
            _run_spotify_import_session(session, repository, import_session)
        else:
            raise ValueError(f"Unsupported import source: {import_session.source}")
    except Exception:
        summary = _session_summary(import_session)
        import_session.status = "failed"
        import_session.completed_at = _utc_now()
        _append_import_log(
            session,
            import_session,
            level="error",
            stage=summary.progress_label,
            message="Import failed. Check server logs for traceback.",
        )
        _set_import_progress(
            import_session,
            summary,
            label="Failed",
            current=summary.progress_current,
            total=summary.progress_total,
        )
        session.commit()
        raise

    return _build_import_session_summary(import_session)


def import_history(
    session: Session,
    repository: SqliteStateRepository,
) -> list[ImportSessionSummary]:
    rows = session.scalars(
        select(ImportSession)
        .where(ImportSession.user_id == repository.user.id)
        .order_by(ImportSession.started_at.desc(), ImportSession.id.desc())
    ).all()
    return [_build_import_session_summary(row) for row in rows]


def import_session_logs(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
    *,
    limit: int = 100,
    order: str = "asc",
) -> list[ImportSessionLogEntry]:
    import_session = session.scalars(
        select(ImportSession).where(
            ImportSession.id == import_session_id,
            ImportSession.user_id == repository.user.id,
        )
    ).first()
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")

    safe_limit = max(1, min(limit, 500))
    query = select(ImportSessionLog).where(
        ImportSessionLog.import_session_id == import_session.id
    )
    if order == "desc":
        query = query.order_by(ImportSessionLog.created_at.desc(), ImportSessionLog.id.desc())
    else:
        query = query.order_by(ImportSessionLog.created_at.asc(), ImportSessionLog.id.asc())
    rows = session.scalars(query.limit(safe_limit)).all()
    return [
        ImportSessionLogEntry(
            id=row.id,
            import_session_id=row.import_session_id,
            created_at=row.created_at,
            level=row.level,
            stage=row.stage,
            message=row.message,
            artist=row.artist,
            album=row.album,
            current=row.current,
            total=row.total,
            elapsed_seconds=row.elapsed_seconds,
            metadata=row.metadata_json or {},
        )
        for row in rows
    ]


def resumable_import_session_ids(session: Session) -> list[int]:
    return list(
        session.scalars(
            select(ImportSession.id)
            .where(ImportSession.status.in_(RESUMABLE_IMPORT_STATUSES))
            .order_by(ImportSession.started_at.asc(), ImportSession.id.asc())
        ).all()
    )


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
    if import_session.source == SPOTIFY_IMPORT_SOURCE:
        session.execute(
            delete(SpotifyStreamingEvent).where(
                SpotifyStreamingEvent.import_session_id == import_session.id,
                SpotifyStreamingEvent.user_id == repository.user.id,
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
    session.flush()
    _append_import_log(
        session,
        import_session,
        stage="queued",
        message="Last.fm import queued.",
    )
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


def create_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    *,
    artifact_path: str,
    original_filename: str | None,
    session_name: str | None = None,
) -> ImportCommitResponse:
    import_session = ImportSession(
        user_id=repository.user.id,
        source=SPOTIFY_IMPORT_SOURCE,
        source_user_id=None,
        status="queued",
        session_name=session_name
        or _default_spotify_session_name(original_filename),
        started_at=_utc_now(),
        completed_at=None,
        artifact_path=artifact_path,
        summary_json=_empty_summary().model_dump(),
    )
    session.add(import_session)
    session.flush()
    _append_import_log(
        session,
        import_session,
        stage="queued",
        message="Spotify import queued.",
    )
    session.commit()

    return ImportCommitResponse(
        import_session_id=import_session.id,
        source=SPOTIFY_IMPORT_SOURCE,
        status=import_session.status,
        session_name=import_session.session_name,
        source_user_id=None,
        summary=_session_summary(import_session),
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
    if import_session.status in {"fetching_metadata", "finalizing"}:
        pending_rows = _pending_metadata_rows(session, repository, import_session)
        if pending_rows:
            _resume_lastfm_metadata_import(session, repository, import_session, pending_rows)
            return

    import_session.status = "fetching_lastfm"
    _append_import_log(
        session,
        import_session,
        stage="fetching_lastfm",
        message="Fetching Last.fm scrobbles.",
    )
    session.commit()

    fetch_summary = _empty_summary()
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
    timer.finish()
    summary = _lastfm_raw_import_summary(rows, [])
    timer.summary = summary
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
    timer.start("storing_scrobbles")
    _append_import_log(
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
    previous_timings = dict(summary.stage_timings or {})
    summary = _lastfm_raw_import_summary(rows, raw_rows)
    summary.stage_timings = previous_timings
    timer.summary = summary
    timer.finish()
    import_session.status = "grouping_album_sessions"
    _set_import_progress(
        import_session,
        summary,
        label="Grouping album sessions",
        current=0,
        total=0,
    )
    timer.start("grouping_album_sessions")
    _append_import_log(
        session,
        import_session,
        stage="grouping_album_sessions",
        message="Grouping Last.fm scrobbles into album sessions.",
    )
    session.commit()

    candidate_rows = [row for row in raw_rows if row.match_status == "raw_imported"]

    timer.finish()
    import_session.status = "matching_cached_albums"
    timer.start("matching_cached_albums")
    _append_import_log(
        session,
        import_session,
        stage="matching_cached_albums",
        message="Checking saved album metadata.",
    )

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
        metadata_stats=metadata_stats,
        progress_callback=update_cached_match_progress,
    )
    timer.finish()
    _apply_lastfm_candidate_summary(summary, cached_candidates)
    _apply_metadata_stats(summary, metadata_stats)
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
        unique_pending_total = len({row.candidate_key for row in pending_rows if row.candidate_key})
        _apply_metadata_stats(summary, metadata_stats, current=0, total=unique_pending_total)
        _set_import_progress(
            import_session,
            summary,
            label="Fetching MusicBrainz metadata",
            current=0,
            total=unique_pending_total,
        )
        timer.start("fetching_metadata")
        _append_import_log(
            session,
            import_session,
            stage="fetching_metadata",
            message="Looking up missing album metadata.",
            current=0,
            total=unique_pending_total,
        )
        session.commit()

        remote_candidates = _process_pending_metadata_incrementally(
            session=session,
            repository=repository,
            import_session=import_session,
            pending_rows=pending_rows,
            cached_candidates=cached_candidates,
            summary=summary,
            metadata_stats=metadata_stats,
        )
        timer.finish()
        final_candidates = [
            candidate
            for candidate in cached_candidates
            if candidate.status not in {"no_tracklist", "pending_metadata"}
        ] + remote_candidates
        _apply_lastfm_candidate_summary(summary, final_candidates)
        _apply_metadata_stats(summary, metadata_stats)
        session.commit()
    else:
        final_candidates = cached_candidates

    import_session.status = "finalizing"
    timer.start("finalizing")
    _append_import_log(
        session,
        import_session,
        stage="finalizing",
        message="Finalizing Last.fm import.",
    )
    _set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    session.commit()

    timer.finish()
    _apply_lastfm_candidate_summary(summary, final_candidates)
    _apply_metadata_stats(summary, metadata_stats)
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
    _append_import_log(
        session,
        import_session,
        stage="completed",
        message="Last.fm import completed.",
    )
    session.commit()


def _run_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    artifact_path = import_session.artifact_path
    existing_raw_events = _spotify_streaming_event_count(session, repository, import_session)
    existing_import_rows = _imported_event_count_for_session(session, repository, import_session)
    if existing_raw_events and (
        not artifact_path
        or import_session.status in {"fetching_metadata", "finalizing"}
        or existing_import_rows
    ):
        _resume_spotify_import_session(session, repository, import_session)
        return
    if not artifact_path:
        raise ValueError("Spotify import ZIP is missing; re-upload is required.")

    summary = _empty_summary()
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    try:
        import_session.status = "validating_zip"
        timer.start("validating_zip")
        _set_import_progress(
            import_session,
            summary,
            label="Validating Spotify ZIP",
            current=0,
            total=0,
        )
        _append_import_log(
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
        timer.finish()
        summary.total_rows = len(history_entries)
        _set_import_progress(
            import_session,
            summary,
            label="Parsing Spotify history",
            current=0,
            total=len(history_entries),
        )
        import_session.status = "parsing_spotify_history"
        timer.start("parsing_spotify_history")
        _append_import_log(
            session,
            import_session,
            stage="parsing_spotify_history",
            message="Parsing Spotify history files.",
            current=0,
            total=len(history_entries),
        )
        session.commit()

        for index, entry in enumerate(history_entries, start=1):
            _set_import_progress(
                import_session,
                summary,
                label="Parsing Spotify history",
                current=index,
                total=len(history_entries),
            )
            session.commit()

        timer.finish()
        _set_import_progress(
            import_session,
            summary,
            label="Storing Spotify plays",
            current=0,
            total=0,
        )
        import_session.status = "storing_streaming_events"
        timer.start("storing_streaming_events")
        _append_import_log(
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
            _set_import_progress(
                import_session,
                summary_update,
                label="Storing Spotify plays",
                current=summary_update.progress_current,
                total=summary_update.progress_total,
            )
            session.commit()

        summary = _stream_persist_spotify_streaming_events(
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

        import_session.status = "grouping_album_sessions"
        _set_import_progress(
            import_session,
            summary,
            label="Grouping album sessions",
            current=0,
            total=0,
        )
        timer.start("grouping_album_sessions")
        _append_import_log(
            session,
            import_session,
            stage="grouping_album_sessions",
            message="Grouping Spotify plays into album sessions.",
        )
        session.commit()

        timer.finish()
        import_session.status = "matching_cached_albums"
        timer.start("matching_cached_albums")
        _append_import_log(
            session,
            import_session,
            stage="matching_cached_albums",
            message="Checking saved album metadata.",
        )

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

        cached_candidates = _build_spotify_candidates_from_streaming_events(
            session=session,
            repository=repository,
            import_session=import_session,
            allow_remote_metadata=False,
            metadata_stats=metadata_stats,
            progress_callback=update_cached_match_progress,
        )
        timer.finish()
        _apply_lastfm_candidate_summary(summary, cached_candidates)
        _apply_metadata_stats(summary, metadata_stats)
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
            unique_pending_total = len(
                {_album_match_key(row.artist, row.album) for row in pending_rows}
            )
            _apply_metadata_stats(summary, metadata_stats, current=0, total=unique_pending_total)
            _set_import_progress(
                import_session,
                summary,
                label="Fetching MusicBrainz metadata",
                current=0,
                total=unique_pending_total,
            )
            timer.start("fetching_metadata")
            _append_import_log(
                session,
                import_session,
                stage="fetching_metadata",
                message="Looking up missing album metadata.",
                current=0,
                total=unique_pending_total,
            )
            session.commit()

            remote_candidates = _process_pending_metadata_incrementally(
                session=session,
                repository=repository,
                import_session=import_session,
                pending_rows=pending_rows,
                cached_candidates=cached_candidates,
                summary=summary,
                metadata_stats=metadata_stats,
            )
            timer.finish()
            final_candidates = [
                candidate
                for candidate in cached_candidates
                if candidate.status not in {"no_tracklist", "pending_metadata"}
            ] + remote_candidates
            _apply_lastfm_candidate_summary(summary, final_candidates)
            _apply_metadata_stats(summary, metadata_stats)
            session.commit()
        else:
            final_candidates = cached_candidates

        import_session.status = "finalizing"
        timer.start("finalizing")
        _append_import_log(
            session,
            import_session,
            stage="finalizing",
            message="Finalizing Spotify import.",
        )
        _set_import_progress(
            import_session,
            summary,
            label="Finalizing",
            current=summary.progress_total or len(final_candidates),
            total=summary.progress_total or len(final_candidates),
        )
        session.commit()

        timer.finish()
        _apply_lastfm_candidate_summary(summary, final_candidates)
        _apply_metadata_stats(summary, metadata_stats)
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
        _append_import_log(
            session,
            import_session,
            stage="completed",
            message="Spotify import completed.",
        )
        session.commit()
    finally:
        if import_session.status in TERMINAL_IMPORT_STATUSES:
            _delete_file_quietly(artifact_path)
            import_session.artifact_path = None
        session.commit()


def _resume_lastfm_metadata_import(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    pending_rows: list[ImportedListeningEvent],
) -> None:
    summary = _session_summary(import_session)
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    _append_import_log(
        session,
        import_session,
        stage="fetching_metadata",
        message="Resuming Last.fm import from pending metadata candidates.",
    )
    import_session.status = "fetching_metadata"
    timer.start("fetching_metadata")
    remote_candidates = _process_pending_metadata_incrementally(
        session=session,
        repository=repository,
        import_session=import_session,
        pending_rows=pending_rows,
        cached_candidates=[],
        summary=summary,
        metadata_stats=metadata_stats,
    )
    timer.finish()
    _apply_lastfm_candidate_summary(summary, remote_candidates)
    _apply_metadata_stats(summary, metadata_stats)
    import_session.status = "finalizing"
    _set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(remote_candidates),
        total=summary.progress_total or len(remote_candidates),
    )
    session.commit()
    import_session.status = "completed"
    import_session.completed_at = _utc_now()
    _set_import_progress(
        import_session,
        summary,
        label="Completed",
        current=summary.progress_total or len(remote_candidates),
        total=summary.progress_total or len(remote_candidates),
    )
    import_session.summary_json = summary.model_dump()
    _append_import_log(
        session,
        import_session,
        stage="completed",
        message="Last.fm import completed after resume.",
    )
    session.commit()


def _resume_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> None:
    summary = _session_summary(import_session)
    timer = ImportStageTimer(import_session.id, summary)
    metadata_stats = ImportMetadataStats()
    _append_import_log(
        session,
        import_session,
        stage=import_session.status,
        message="Resuming Spotify import from persisted progress.",
    )

    if _imported_event_count_for_session(session, repository, import_session) == 0:
        import_session.status = "matching_cached_albums"
        timer.start("matching_cached_albums")
        _set_import_progress(
            import_session,
            summary,
            label="Matching cached albums",
            current=0,
            total=0,
        )
        session.commit()
        cached_candidates = _build_spotify_candidates_from_streaming_events(
            session=session,
            repository=repository,
            import_session=import_session,
            allow_remote_metadata=False,
            metadata_stats=metadata_stats,
        )
        timer.finish()
        _apply_lastfm_candidate_summary(summary, cached_candidates)
        _apply_metadata_stats(summary, metadata_stats)
        _process_lastfm_candidates(
            session=session,
            repository=repository,
            candidates=cached_candidates,
        )
        session.commit()
    else:
        cached_candidates = []

    pending_rows = _pending_metadata_rows(session, repository, import_session)
    if pending_rows:
        import_session.status = "fetching_metadata"
        timer.start("fetching_metadata")
        remote_candidates = _process_pending_metadata_incrementally(
            session=session,
            repository=repository,
            import_session=import_session,
            pending_rows=pending_rows,
            cached_candidates=cached_candidates,
            summary=summary,
            metadata_stats=metadata_stats,
        )
        timer.finish()
        final_candidates = cached_candidates + remote_candidates
        _apply_lastfm_candidate_summary(summary, final_candidates)
        _apply_metadata_stats(summary, metadata_stats)
    else:
        final_candidates = cached_candidates

    import_session.status = "finalizing"
    timer.start("finalizing")
    _set_import_progress(
        import_session,
        summary,
        label="Finalizing",
        current=summary.progress_total or len(final_candidates),
        total=summary.progress_total or len(final_candidates),
    )
    session.commit()

    timer.finish()
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
    _append_import_log(
        session,
        import_session,
        stage="completed",
        message="Spotify import completed after resume.",
    )
    if import_session.artifact_path:
        _delete_file_quietly(import_session.artifact_path)
        import_session.artifact_path = None
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


def _stream_persist_spotify_streaming_events(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    artifact_path: str,
    history_entries: list[Any],
    progress_callback: Any | None = None,
) -> ImportPreviewSummary:
    summary = _empty_summary()
    batch: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    def flush_batch() -> None:
        if not batch:
            return
        statement = sqlite_insert(SpotifyStreamingEvent).values(batch)
        result = session.execute(statement.on_conflict_do_nothing())
        summary.new_event_rows += result.rowcount or 0
        batch.clear()
        session.flush()

    for entry in history_entries:
        for row in iter_spotify_history_events(artifact_path, entry.filename):
            summary.total_rows += 1
            summary.progress_current = summary.total_rows
            summary.progress_total = summary.total_rows

            if not row.played_at or not row.artist_name or not row.track_name:
                summary.failed_rows += 1
                if progress_callback:
                    progress_callback(summary)
                continue

            fingerprint = spotify_streaming_fingerprint(row)
            if fingerprint in seen_fingerprints:
                summary.duplicate_rows += 1
                if progress_callback:
                    progress_callback(summary)
                continue
            seen_fingerprints.add(fingerprint)

            batch.append(
                {
                    "user_id": repository.user.id,
                    "import_session_id": import_session.id,
                    "event_fingerprint": fingerprint,
                    "played_at": row.played_at,
                    "ms_played": row.ms_played,
                    "spotify_track_uri": row.spotify_track_uri,
                    "track_name": row.track_name,
                    "artist_name": row.artist_name,
                    "album_name": row.album_name,
                    "platform": row.platform,
                    "country": row.country,
                    "reason_start": row.reason_start,
                    "reason_end": row.reason_end,
                    "skipped": row.skipped,
                    "offline": row.offline,
                    "raw_payload": row.raw_payload,
                }
            )
            if not row.album_name:
                summary.missing_album_rows += 1

            if len(batch) >= SPOTIFY_IMPORT_INSERT_BATCH_SIZE:
                before_inserted = summary.new_event_rows
                flush_batch()
                summary.duplicate_rows += max(
                    0,
                    SPOTIFY_IMPORT_INSERT_BATCH_SIZE
                    - (summary.new_event_rows - before_inserted),
                )
                if progress_callback:
                    progress_callback(summary)
            elif progress_callback:
                progress_callback(summary)

    before_inserted = summary.new_event_rows
    final_batch_size = len(batch)
    flush_batch()
    summary.duplicate_rows += max(
        0,
        final_batch_size - (summary.new_event_rows - before_inserted),
    )
    summary.progress_current = summary.total_rows
    summary.progress_total = summary.total_rows
    if progress_callback:
        progress_callback(summary)
    return summary


def _spotify_streaming_event_count(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> int:
    return session.scalar(
        select(func.count())
        .select_from(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session.id,
            SpotifyStreamingEvent.user_id == repository.user.id,
        )
    ) or 0


def _imported_event_count_for_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> int:
    return session.scalar(
        select(func.count())
        .select_from(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == repository.user.id,
        )
    ) or 0


def _pending_metadata_rows(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == repository.user.id,
            ImportedListeningEvent.match_status == "pending_metadata",
        )
    ).all()


def _build_spotify_candidates_from_streaming_events(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    *,
    allow_remote_metadata: bool,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[LastfmCandidate]:
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = _existing_album_index(repository)
    candidates: list[LastfmCandidate] = []
    current_key: tuple[str, str] | None = None
    current_events: list[NormalizedImportEvent] = []

    rows = session.scalars(
        select(SpotifyStreamingEvent)
        .where(
            SpotifyStreamingEvent.import_session_id == import_session.id,
            SpotifyStreamingEvent.user_id == repository.user.id,
            SpotifyStreamingEvent.artist_name.is_not(None),
            SpotifyStreamingEvent.album_name.is_not(None),
            SpotifyStreamingEvent.played_at.is_not(None),
        )
        .order_by(
            func.lower(SpotifyStreamingEvent.artist_name),
            func.lower(SpotifyStreamingEvent.album_name),
            SpotifyStreamingEvent.played_at,
            SpotifyStreamingEvent.id,
        )
    ).yield_per(1000)

    def process_group(events: list[NormalizedImportEvent]) -> None:
        if not events:
            return
        for chunk in _split_lastfm_sessions(events):
            candidate = _build_lastfm_candidate(
                repository=repository,
                events=chunk,
                source_user_id=None,
                metadata_cache=metadata_cache,
                existing_album_index=existing_album_index,
                load_metadata=True,
                allow_remote_metadata=allow_remote_metadata,
                metadata_stats=metadata_stats,
            )
            candidates.append(candidate)

    for row in rows:
        key = (
            (row.artist_name or "").casefold(),
            (row.album_name or "").casefold(),
        )
        if current_key is not None and key != current_key:
            process_group(current_events)
            current_events = []
        current_key = key
        current_events.append(_spotify_streaming_event_to_import_event(row))
    process_group(current_events)

    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    _persist_spotify_candidate_rows(
        session=session,
        repository=repository,
        import_session=import_session,
        candidates=candidates,
    )

    total_candidates = len(candidates)
    if progress_callback:
        for index in range(1, total_candidates + 1):
            if index == 1 or index % 5 == 0 or index == total_candidates:
                progress_callback(index, total_candidates, candidates[:index])
    return candidates


def _build_spotify_candidates_from_imported_events(
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    allow_remote_metadata: bool,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[LastfmCandidate]:
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = _existing_album_index(repository)
    candidates: list[LastfmCandidate] = []
    grouped_rows: dict[tuple[str, str], list[ImportedListeningEvent]] = defaultdict(list)
    for row in imported_rows:
        grouped_rows[_album_match_key(row.artist, row.album)].append(row)

    total = len(grouped_rows)
    for index, rows_for_album in enumerate(grouped_rows.values(), start=1):
        for row in rows_for_album:
            streaming_event_ids = row.raw_payload.get("_spotify_streaming_event_ids") or []
            streaming_events = repository.session.scalars(
                select(SpotifyStreamingEvent)
                .where(
                    SpotifyStreamingEvent.user_id == repository.user.id,
                    SpotifyStreamingEvent.id.in_(streaming_event_ids),
                )
                .order_by(SpotifyStreamingEvent.played_at, SpotifyStreamingEvent.id)
            ).all()
            events = [
                _spotify_streaming_event_to_import_event(streaming_event)
                for streaming_event in streaming_events
            ]
            if not events:
                continue
            candidate = _build_lastfm_candidate(
                repository=repository,
                events=events,
                source_user_id=None,
                metadata_cache=metadata_cache,
                existing_album_index=existing_album_index,
                load_metadata=True,
                allow_remote_metadata=allow_remote_metadata,
                metadata_stats=metadata_stats,
            )
            candidate.candidate_key = row.candidate_key or candidate.candidate_key
            candidates.append(candidate)
        if progress_callback and (index == 1 or index % 5 == 0 or index == total):
            progress_callback(index, total, candidates)

    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    return candidates


def _build_remote_candidates_for_imported_rows(
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    metadata_stats: ImportMetadataStats,
) -> list[LastfmCandidate]:
    if imported_rows and imported_rows[0].source == SPOTIFY_IMPORT_SOURCE:
        return _build_spotify_candidates_from_imported_events(
            repository=repository,
            imported_rows=imported_rows,
            allow_remote_metadata=True,
            metadata_stats=metadata_stats,
        )
    return _build_lastfm_candidates_from_imported_events(
        repository=repository,
        imported_rows=imported_rows,
        allow_remote_metadata=True,
        metadata_stats=metadata_stats,
    )


def _process_pending_metadata_incrementally(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    pending_rows: list[ImportedListeningEvent],
    cached_candidates: list[LastfmCandidate],
    summary: ImportPreviewSummary,
    metadata_stats: ImportMetadataStats,
) -> list[LastfmCandidate]:
    grouped_rows: dict[tuple[str, str], list[ImportedListeningEvent]] = defaultdict(list)
    for row in pending_rows:
        grouped_rows[_album_match_key(row.artist, row.album)].append(row)

    remote_candidates: list[LastfmCandidate] = []
    total = len(grouped_rows)
    base_candidates = [
        candidate
        for candidate in cached_candidates
        if candidate.status not in {"no_tracklist", "pending_metadata"}
    ]
    _apply_metadata_stats(summary, metadata_stats, current=0, total=total)
    _set_import_progress(
        import_session,
        summary,
        label="Fetching MusicBrainz metadata",
        current=0,
        total=total,
    )

    for index, rows_for_album in enumerate(grouped_rows.values(), start=1):
        artist = rows_for_album[0].artist
        album = rows_for_album[0].album
        started_at = time.perf_counter()
        candidates = _build_remote_candidates_for_imported_rows(
            repository,
            rows_for_album,
            metadata_stats=metadata_stats,
        )
        _process_lastfm_candidates(
            session=session,
            repository=repository,
            candidates=candidates,
        )
        remote_candidates.extend(candidates)
        elapsed = time.perf_counter() - started_at
        combined_candidates = base_candidates + remote_candidates
        _apply_lastfm_candidate_summary(summary, combined_candidates)
        _apply_metadata_stats(summary, metadata_stats, current=index, total=total)
        _set_import_progress(
            import_session,
            summary,
            label="Fetching MusicBrainz metadata",
            current=index,
            total=total,
        )
        statuses = sorted({candidate.status for candidate in candidates}) or ["skipped"]
        _append_import_log(
            session,
            import_session,
            stage="fetching_metadata",
            message=f"Checked {artist} - {album}: {', '.join(statuses)}",
            artist=artist,
            album=album,
            current=index,
            total=total,
            elapsed_seconds=round(elapsed, 3),
            metadata={
                "statuses": statuses,
                "cache_hits": summary.metadata_cache_hits,
                "cache_misses": summary.metadata_cache_misses,
                "musicbrainz_requests": summary.musicbrainz_requests,
            },
        )
        import_session.summary_json = summary.model_dump()
        session.commit()
    return remote_candidates


def _persist_spotify_candidate_rows(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    candidates: list[LastfmCandidate],
) -> list[ImportedListeningEvent]:
    persisted: list[ImportedListeningEvent] = []
    for candidate in candidates:
        if candidate.status == "partial_listen":
            continue
        representative = candidate.events[-1]
        streaming_event_ids = [
            event.raw_payload.get("_spotify_streaming_event_id")
            for event in candidate.events
            if event.raw_payload.get("_spotify_streaming_event_id") is not None
        ]
        event = ImportedListeningEvent(
            user_id=repository.user.id,
            import_session_id=import_session.id,
            album_id=None,
            source=SPOTIFY_IMPORT_SOURCE,
            source_user_id=None,
            source_event_id=candidate.candidate_key,
            event_fingerprint=_spotify_candidate_fingerprint(candidate),
            candidate_key=candidate.candidate_key,
            listened_at=candidate.listened_at,
            artist=candidate.artist,
            album=candidate.album,
            track=(
                f"{candidate.unique_scrobbled_tracks} unique Spotify tracks"
            ),
            source_label=SPOTIFY_IMPORT_SOURCE,
            rating=None,
            notes=None,
            match_status="raw_imported",
            match_confidence=None,
            error_message=None,
            raw_payload={
                "_spotify_streaming_event_ids": streaming_event_ids,
                "_representative_track": representative.track,
                "_track_count": len(streaming_event_ids),
            },
        )
        session.add(event)
        persisted.append(event)
    session.flush()
    return persisted


def _spotify_streaming_event_to_import_event(
    row: SpotifyStreamingEvent,
) -> NormalizedImportEvent:
    return NormalizedImportEvent(
        listened_at=row.played_at,
        artist=row.artist_name,
        album=row.album_name,
        track=row.track_name,
        source=SPOTIFY_IMPORT_SOURCE,
        source_user_id=None,
        source_event_id=str(row.id),
        source_label=SPOTIFY_IMPORT_SOURCE,
        rating=None,
        notes=None,
        raw_payload={
            **(row.raw_payload or {}),
            "_spotify_streaming_event_id": row.id,
            "_spotify_track_uri": row.spotify_track_uri,
            "_spotify_track_name": row.track_name,
            "_spotify_ms_played": row.ms_played,
        },
    )


def _spotify_candidate_fingerprint(candidate: LastfmCandidate) -> str:
    return hashlib.sha256(
        "|".join(
            [
                SPOTIFY_IMPORT_SOURCE,
                candidate.candidate_key,
            ]
        ).encode("utf-8")
    ).hexdigest()


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
    metadata_stats: ImportMetadataStats | None = None,
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
        metadata_stats=metadata_stats,
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
    metadata_stats: ImportMetadataStats | None = None,
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
            metadata_stats=metadata_stats,
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
    metadata_stats: ImportMetadataStats | None = None,
) -> LastfmCandidate:
    artist = events[0].artist or "Unknown Artist"
    album = events[0].album or "Unknown Album"
    listened_at = max(event.listened_at for event in events if event.listened_at)
    matched_album = existing_album_index.get(_album_match_key(artist, album))
    matched_album_id = matched_album.album_id if matched_album else None
    unique_track_names = {
        _normalize_track_name(event.track)
        for event in events
        if _normalize_track_name(event.track)
    }
    unique_track_identities = {
        _normalize_import_event_track_identity(event)
        for event in events
        if _normalize_import_event_track_identity(event)
    }
    remote_metadata_allowed = (
        allow_remote_metadata
        and _candidate_has_remote_metadata_evidence(events, unique_track_identities)
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
            entry_source=events[0].source,
            metadata_stats=metadata_stats,
        )
        if load_metadata
        else None
    )

    matched_track_count = 0
    total_track_count = 0
    confidence = 25
    status = "partial_listen"
    if not load_metadata:
        matched_track_count = len(unique_track_identities)
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
        matched_track_count = len(unique_track_names & metadata_tracks)
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
                f"Matched {matched_track_count} of {total_track_count or len(unique_track_names)} tracks. "
                "This does not count as a completed album listen."
            )
    elif not _candidate_has_remote_metadata_evidence(events, unique_track_identities):
        status = "partial_listen"
        detail = (
            f"Only {len(unique_track_identities)} unique tracks were available; skipped remote metadata "
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

    candidate_key = _import_candidate_key(events[0].source, source_user_id, artist, album, events)
    return LastfmCandidate(
        candidate_key=candidate_key,
        artist=artist,
        album=album,
        listened_at=listened_at,
        events=events,
        matched_album_id=matched_album_id,
        matched_track_count=matched_track_count,
        total_track_count=total_track_count,
        unique_scrobbled_tracks=len(unique_track_identities),
        status=status,
        status_detail=detail,
        confidence=confidence,
        metadata=metadata,
    )


def _candidate_has_remote_metadata_evidence(
    events: list[NormalizedImportEvent],
    unique_track_identities: set[str],
) -> bool:
    if events and events[0].source == SPOTIFY_IMPORT_SOURCE:
        total_ms_played = sum(
            int(event.raw_payload.get("_spotify_ms_played") or event.raw_payload.get("ms_played") or 0)
            for event in events
        )
        unique_tracks = len(unique_track_identities)
        return unique_tracks >= SPOTIFY_REMOTE_METADATA_ALWAYS_UNIQUE_TRACKS or (
            unique_tracks >= SPOTIFY_REMOTE_METADATA_MIN_UNIQUE_TRACKS
            and total_ms_played >= SPOTIFY_REMOTE_METADATA_MIN_MS_PLAYED
        )
    return len(unique_track_identities) >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS


def _is_lastfm_importable_album_metadata(
    metadata: dict[str, Any],
    total_track_count: int,
) -> bool:
    confidence = album_metadata_service.metadata_match_confidence(metadata)
    if confidence < album_metadata_service.IMPORT_MATCH_CONFIDENCE:
        return False

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
    entry_source: str = "lastfm",
    metadata_stats: ImportMetadataStats | None = None,
) -> dict[str, Any] | None:
    cache_key = (artist.casefold(), album.casefold())
    if cache_key in metadata_cache:
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return metadata_cache[cache_key]

    if matched_album_id is not None and matched_album_record and matched_album_record.get("tracklist"):
        metadata_cache[cache_key] = matched_album_record
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return matched_album_record

    cached = _read_album_metadata_cache(session, artist, album)
    if cached is not _ALBUM_METADATA_CACHE_MISS:
        metadata_cache[cache_key] = cached if isinstance(cached, dict) else None
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return metadata_cache[cache_key]

    if not allow_remote_metadata:
        metadata_cache[cache_key] = None
        return None

    started_at = time.perf_counter()
    if metadata_stats is not None:
        metadata_stats.cache_misses += 1
    try:
        metadata = album_metadata_service.get_album_metadata_for_import_matching(artist, album)
        if metadata:
            metadata["entry_source"] = entry_source
            metadata.pop("_refresh_warnings", None)
    except Exception:
        if metadata_stats is not None:
            metadata_stats.lookup_seconds.append(time.perf_counter() - started_at)
        metadata_cache[cache_key] = None
        return None
    if metadata_stats is not None:
        metadata_stats.lookup_seconds.append(time.perf_counter() - started_at)

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
        "|".join(
            [
                "musicbrainz-import-v2",
                artist.strip().casefold(),
                album.strip().casefold(),
            ]
        ).encode("utf-8")
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


def _import_candidate_key(
    source: str,
    source_user_id: str | None,
    artist: str,
    album: str,
    events: list[NormalizedImportEvent],
) -> str:
    payload = "|".join(
        [
            source,
            source_user_id or "",
            artist.casefold(),
            album.casefold(),
            events[0].listened_at or "",
            events[-1].listened_at or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lastfm_candidate_key(
    source_user_id: str | None,
    artist: str,
    album: str,
    events: list[NormalizedImportEvent],
) -> str:
    return _import_candidate_key("lastfm", source_user_id, artist, album, events)


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
        stage_timings={},
        metadata_lookup_current=0,
        metadata_lookup_total=0,
        metadata_cache_hits=0,
        metadata_cache_misses=0,
        musicbrainz_requests=0,
        musicbrainz_lookup_seconds_avg=None,
        musicbrainz_lookup_seconds_p95=None,
        estimated_seconds_remaining=None,
    )


def _default_session_name(request: ImportPreviewRequest, source_user_id: str | None) -> str:
    if source_user_id:
        return f"Last.fm import for {source_user_id}"
    return "Last.fm import"


def _default_spotify_session_name(original_filename: str | None) -> str:
    filename = clean_text(original_filename)
    if filename:
        return f"Spotify import from {filename}"
    return "Spotify import"


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


def _normalize_import_event_track_identity(event: NormalizedImportEvent) -> str:
    spotify_track_uri = clean_text(event.raw_payload.get("_spotify_track_uri"))
    if spotify_track_uri:
        return spotify_track_uri.casefold()
    return _normalize_track_name(event.track)


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


def _delete_file_quietly(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
