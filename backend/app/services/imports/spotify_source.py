"""Queue Spotify ZIP uploads, store raw plays and resolve their catalog identities."""

import hashlib
import os
from typing import Any

import structlog
from sqlalchemy.orm import Session

from backend.app.models import ImportSession
from backend.app.repositories import (
    import_session_repository as import_sessions,
    spotify_import_repository as import_spotify,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportCommitResponse, ImportPreviewSummary
from backend.app.services import spotify_catalog_service
from backend.app.services.import_parsers import clean_text
from backend.app.services.spotify_import_parser import (
    SpotifyZipHistoryEntry,
    iter_spotify_history_events_with_provenance,
    spotify_streaming_fingerprint,
)

from .events import SPOTIFY_IMPORT_SOURCE, utc_now
from .progress import append_import_log, commit_response, empty_summary


SPOTIFY_IMPORT_INSERT_BATCH_SIZE = 1_000


def create_spotify_import_session(
    session: Session,
    repository: SqliteStateRepository,
    *,
    artifact_path: str,
    original_filename: str | None,
    session_name: str | None = None,
) -> ImportCommitResponse:
    file_size_bytes = os.path.getsize(artifact_path)
    file_sha256 = _file_sha256(artifact_path)
    duplicate_session_id = import_sessions.duplicate_spotify_session(
        session, repository.user.id, file_sha256,
    )
    import_session = import_sessions.stage_session(
        session,
        user_id=repository.user.id,
        source=SPOTIFY_IMPORT_SOURCE,
        source_user_id=None,
        status="queued",
        session_name=session_name
        or _default_spotify_session_name(original_filename),
        started_at=utc_now(),
        completed_at=None,
        artifact_path=artifact_path,
        original_filename=original_filename,
        file_size_bytes=file_size_bytes,
        file_sha256=file_sha256,
        duplicate_of_import_session_id=duplicate_session_id,
        summary_json=empty_summary().model_dump(),
    )
    append_import_log(
        session,
        import_session,
        stage="queued",
        message="Spotify import queued.",
        metadata={
            "original_filename": original_filename,
            "file_size_bytes": file_size_bytes,
            "file_sha256": file_sha256,
            "duplicate_of_import_session_id": duplicate_session_id,
        },
    )
    if duplicate_session_id is not None:
        append_import_log(
            session,
            import_session,
            stage="queued",
            level="warning",
            message=(
                "This Spotify ZIP has the same SHA-256 fingerprint as "
                f"import session {duplicate_session_id}."
            ),
            metadata={
                "duplicate_of_import_session_id": duplicate_session_id,
                "file_sha256": file_sha256,
            },
        )
    session.commit()
    if duplicate_session_id is not None:
        structlog.get_logger(__name__).warning(
            "spotify_import_duplicate_archive", user_id=repository.user.id,
            import_session_id=import_session.id, duplicate_of_session_id=duplicate_session_id,
        )

    return commit_response(import_session)


def store_streaming_events(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    artifact_path: str,
    history_entries: list[SpotifyZipHistoryEntry],
    progress_callback: Any | None = None,
) -> ImportPreviewSummary:
    summary = empty_summary()
    batch: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    def flush_batch() -> None:
        if not batch:
            return
        inserted = import_spotify.insert_streaming_batch(session, batch)
        summary.new_event_rows += inserted
        summary.duplicate_rows += max(0, len(batch) - inserted)
        batch.clear()

    for entry in history_entries:
        for sourced_row in iter_spotify_history_events_with_provenance(
            artifact_path,
            entry.filename,
        ):
            row = sourced_row.event
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

            batch.append({
                **vars(row), "user_id": repository.user.id, "import_session_id": import_session.id,
                "event_fingerprint": fingerprint,
                "source_file": sourced_row.source_file, "source_index": sourced_row.source_index,
                "spotify_track_id": spotify_catalog_service.spotify_track_id_from_uri(row.spotify_track_uri),
            })
            if not row.album_name:
                summary.missing_album_rows += 1

            if len(batch) >= SPOTIFY_IMPORT_INSERT_BATCH_SIZE:
                flush_batch()
            if progress_callback:
                progress_callback(summary)

    flush_batch()
    summary.progress_current = summary.total_rows
    summary.progress_total = summary.total_rows
    if progress_callback:
        progress_callback(summary)
    return summary


def resolve_spotify_catalog_for_import(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    summary: ImportPreviewSummary,
) -> None:
    rows = import_spotify.unresolved_catalog_rows(session, repository.user.id, import_session.id)
    track_uris = sorted({row.spotify_track_uri for row in rows if row.spotify_track_uri})
    if not track_uris:
        summary.spotify_catalog_fallback_rows = import_spotify.fallback_count(
            session, repository.user.id, import_session.id,
        )
        if summary.spotify_catalog_fallback_rows:
            # No URIs remain to look up; earlier attempts may still need fallback.
            structlog.get_logger(__name__).info(
                "spotify_catalog_fallback", reason="no_unresolved_track_uris",
                unique_track_ids=0, fallback_source_rows=summary.spotify_catalog_fallback_rows,
            )
        return

    try:
        resolved = spotify_catalog_service.resolve_tracks_by_uri(track_uris)
    except spotify_catalog_service.SpotifyCatalogUnavailable as exc:
        summary.spotify_catalog_fallback_rows = import_spotify.fallback_count(
            session, repository.user.id, import_session.id,
        )
        status_code = getattr(exc.__cause__, "http_status", None)
        structlog.get_logger(__name__).warning(
            "spotify_catalog_fallback", reason="catalog_unavailable",
            failure_category="rate_limited" if status_code == 429 else "unavailable",
            status_code=status_code,
            unique_track_ids=len(track_uris), fallback_source_rows=summary.spotify_catalog_fallback_rows,
        )
        append_import_log(
            session,
            import_session,
            stage="resolving_spotify_catalog",
            level="warning",
            message=f"Spotify catalog lookup unavailable; falling back to local metadata matching: {exc}",
            current=0,
            total=len(track_uris),
        )
        return

    for row in rows:
        uri = spotify_catalog_service.spotify_track_uri(
            spotify_catalog_service.spotify_track_id_from_uri(row.spotify_track_uri)
        )
        catalog_track = resolved.get(uri or "")
        raw_payload = dict(row.raw_payload or {})
        if catalog_track is None:
            raw_payload["_spotify_catalog_status"] = "not_found"
            import_spotify.mark_catalog_missing(row, raw_payload)
            continue

        raw_payload.update(
            {
                "_spotify_catalog_status": "resolved",
                "_spotify_album_id": catalog_track.album_id,
                "_spotify_album_name": catalog_track.album_name,
                "_spotify_album_artist_name": catalog_track.album_artist_name,
                "_spotify_album_total_tracks": catalog_track.album_total_tracks,
                "_spotify_album_type": catalog_track.album_type,
                "_spotify_disc_number": catalog_track.disc_number,
                "_spotify_track_number": catalog_track.track_number,
                "_spotify_album_images": catalog_track.album_images,
                "_spotify_album_release_date": catalog_track.album_release_date,
            }
        )
        import_spotify.record_catalog_match(
            row,
            track_id=catalog_track.track_id,
            album_id=catalog_track.album_id,
            album_name=catalog_track.album_name,
            album_artist_name=catalog_track.album_artist_name,
            total_tracks=catalog_track.album_total_tracks,
            album_type=catalog_track.album_type,
            disc_number=catalog_track.disc_number,
            track_number=catalog_track.track_number,
            raw_payload=raw_payload,
        )

    session.flush()
    summary.spotify_catalog_resolved_tracks = len(resolved)
    summary.spotify_catalog_unresolved_tracks = max(0, len(track_uris) - len(resolved))
    summary.spotify_catalog_fallback_rows = import_spotify.fallback_count(
        session, repository.user.id, import_session.id,
    )
    append_import_log(
        session,
        import_session,
        stage="resolving_spotify_catalog",
        message=(
            f"Resolved {summary.spotify_catalog_resolved_tracks} Spotify catalog tracks; "
            f"{summary.spotify_catalog_unresolved_tracks} unresolved."
        ),
        current=summary.spotify_catalog_resolved_tracks,
        total=len(track_uris),
    )


def _default_spotify_session_name(original_filename: str | None) -> str:
    filename = clean_text(original_filename)
    if filename:
        return f"Spotify import from {filename}"
    return "Spotify import"


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def delete_file_quietly(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        return
