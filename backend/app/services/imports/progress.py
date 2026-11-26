"""Persisted progress, timings and API summaries for import sessions."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.database.models import ImportSession
from backend.app.database.repositories import import_session_repository as import_sessions
from backend.app.schemas import (
    ImportCommitResponse,
    ImportPreviewSummary,
    ImportProgressStep,
    ImportSessionSummary,
)

from .events import SPOTIFY_IMPORT_SOURCE, parse_timestamp, utc_now


TERMINAL_IMPORT_STATUSES = {"completed", "failed"}
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
    "resolving_spotify_catalog": "store_source",
    "fetching_lastfm": "store_source",
    "storing_scrobbles": "store_source",
    "grouping_album_sessions": "find_sessions",
    "matching_cached_albums": "check_saved",
    "fetching_metadata": "lookup_missing",
    "finalizing": "finalize",
    "completed": "finalize",
    "failed": "finalize",
}


@dataclass
class ImportMetadataStats:
    cache_hits: int = 0
    cache_misses: int = 0
    lookup_seconds: list[float] = field(default_factory=list)

    @property
    def request_count(self) -> int:
        return len(self.lookup_seconds)

    def apply(self, summary: ImportPreviewSummary, *, current=None, total=None):
        summary.metadata_cache_hits = self.cache_hits
        summary.metadata_cache_misses = self.cache_misses
        summary.musicbrainz_requests = self.request_count
        average = sum(self.lookup_seconds) / self.request_count if self.request_count else None
        summary.musicbrainz_lookup_seconds_avg = round(average, 3) if average is not None else None
        if self.lookup_seconds:
            index = max(0, int(self.request_count * 0.95) - 1)
            summary.musicbrainz_lookup_seconds_p95 = round(sorted(self.lookup_seconds)[index], 3)
        else:
            summary.musicbrainz_lookup_seconds_p95 = None
        if current is not None and total is not None:
            summary.metadata_lookup_current = current
            summary.metadata_lookup_total = total
            if current >= total:
                summary.estimated_seconds_remaining = 0
            elif current > 0 and average is not None:
                summary.estimated_seconds_remaining = round((total - current) * average, 3)


def append_import_log(session, import_session, *, message, level="info", metadata=None, **fields):
    import_sessions.stage_log(
        session, import_session_id=import_session.id, created_at=utc_now(),
        message=message, level=level, metadata_json=metadata or {}, **fields,
    )


def set_import_progress(
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


def stage_completed_import(
    session: Session,
    import_session: ImportSession,
    summary: ImportPreviewSummary,
    *,
    candidate_count: int,
    message: str,
) -> None:
    import_sessions.finish_session(import_session, "completed", utc_now())
    total = summary.progress_total or candidate_count
    set_import_progress(import_session, summary, label="Completed", current=total, total=total)
    append_import_log(session, import_session, stage="completed", message=message)


def session_summary(import_session: ImportSession) -> ImportPreviewSummary:
    summary = ImportPreviewSummary.model_validate(
        import_session.summary_json or empty_summary().model_dump()
    )
    if import_session.source == SPOTIFY_IMPORT_SOURCE:
        summary.spotify_import_original_filename = import_session.original_filename
        summary.spotify_import_file_size_bytes = import_session.file_size_bytes
        summary.spotify_import_sha256 = import_session.file_sha256
        summary.spotify_import_zip_member_count = import_session.zip_member_count
        summary.spotify_import_duplicate_of_session_id = (
            import_session.duplicate_of_import_session_id
        )
    return summary


def _build_progress_steps(
    import_session: ImportSession,
    summary: ImportPreviewSummary,
) -> list[ImportProgressStep]:
    current_key = STATUS_TO_STEP.get(import_session.status)
    current_index = next(
        (index for index, (key, _) in enumerate(IMPORT_STEP_ORDER) if key == current_key),
        len(IMPORT_STEP_ORDER) - 1,
    )
    totals = {
        "store_source": (summary.new_event_rows, summary.total_rows),
        "find_sessions": (summary.distinct_album_candidates, summary.distinct_album_candidates),
        "lookup_missing": (summary.metadata_lookup_current, summary.metadata_lookup_total),
    }
    totals[current_key] = summary.progress_current, summary.progress_total
    steps = []
    for index, (key, label) in enumerate(IMPORT_STEP_ORDER):
        if import_session.status == "failed" and key == current_key:
            status = "failed"
        elif import_session.status == "completed" or index < current_index:
            status = "completed"
        elif index == current_index and import_session.status not in TERMINAL_IMPORT_STATUSES:
            status = "current"
        else:
            status = "pending"

        current, total = totals.get(key, (0, 0))
        detail = _current_step_detail(import_session, summary) if key == current_key else None
        steps.append(ImportProgressStep(key=key, label=label, status=status, current=current, total=total, detail=detail))
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
    if import_session.status in {
        "parsing_spotify_history",
        "storing_streaming_events",
    }:
        return f"{summary.progress_current:,} of {summary.progress_total:,} Spotify plays stored."
    if import_session.status == "resolving_spotify_catalog":
        return (
            f"{summary.spotify_catalog_resolved_tracks:,} Spotify tracks resolved; "
            f"{summary.spotify_catalog_unresolved_tracks:,} unresolved."
        )
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


def build_import_session_summary(import_session: ImportSession) -> ImportSessionSummary:
    summary = session_summary(import_session)
    steps = _build_progress_steps(import_session, summary)
    current_key = STATUS_TO_STEP.get(import_session.status)
    current_step = next((step for step in steps if step.key == current_key), None)
    elapsed_seconds = None
    try:
        started = parse_timestamp(import_session.started_at)
        ended = parse_timestamp(import_session.completed_at) if import_session.completed_at else datetime.now(timezone.utc)
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
        **archive_fields(import_session),
        summary=summary,
        steps=steps,
        current_step_key=current_step.key if current_step else None,
        current_step_label=current_step.label if current_step else None,
        current_step_detail=current_step.detail if current_step else None,
        elapsed_seconds=elapsed_seconds,
        estimated_seconds_remaining=summary.estimated_seconds_remaining,
    )


def empty_summary() -> ImportPreviewSummary:
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
    )


def commit_response(row: ImportSession) -> ImportCommitResponse:
    return ImportCommitResponse(
        import_session_id=row.id, source=row.source, status=row.status, source_user_id=row.source_user_id,
        session_name=row.session_name, summary=session_summary(row), **archive_fields(row),
    )


def archive_fields(row: ImportSession) -> dict:
    return {
        "original_filename": row.original_filename, "file_size_bytes": row.file_size_bytes,
        "file_sha256": row.file_sha256, "zip_member_count": row.zip_member_count,
        "duplicate_of_import_session_id": row.duplicate_of_import_session_id,
    }
