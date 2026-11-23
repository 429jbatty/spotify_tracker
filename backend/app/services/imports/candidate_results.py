"""Apply album-session decisions to the library, import rows and summary."""

from collections import Counter, defaultdict

import structlog
from sqlalchemy.orm import Session

from backend.app.models import ImportedListeningEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary

from .common import parse_timestamp
from .matching import AlbumCandidate
from .metadata import (
    ExistingAlbumMatch,
    album_match_key,
    build_album_record,
    load_existing_albums,
)


def apply_candidate_results(
    session: Session,
    repository: SqliteStateRepository,
    candidates: list[AlbumCandidate],
) -> None:
    album_index = load_existing_albums(repository)
    candidate_keys = sorted(
        {candidate.candidate_key for candidate in candidates if candidate.candidate_key}
    )
    rows_by_candidate_key: dict[str, list[ImportedListeningEvent]] = defaultdict(list)
    for start in range(0, len(candidate_keys), 500):
        batch = candidate_keys[start : start + 500]
        for row in import_events.rows_for_candidates(session, repository.user.id, batch):
            if row.candidate_key:
                rows_by_candidate_key[row.candidate_key].append(row)

    for candidate in candidates:
        candidate_rows = rows_by_candidate_key.get(candidate.candidate_key, [])
        if not candidate_rows:
            continue

        album_id = candidate.matched_album_id
        status = candidate.status
        error_message = candidate.status_detail

        if candidate.status == "matched_existing" and album_id is not None:
            if _has_album_listen_on_utc_date(
                session,
                repository.user.id,
                album_id,
                candidate.listened_at,
            ):
                status = "duplicate_listen"
                candidate.status = status
                error_message = "Album already has a listen on this UTC date."
                album_id = None
            else:
                repository.add_album_listen(album_id, candidate.listened_at)
        elif candidate.status == "new_album":
            record = candidate.metadata or build_album_record(candidate.events[-1])
            album_key = album_match_key(record.get("artist"), record.get("name"))
            existing_album = album_index.get(album_key)
            if existing_album is not None:
                if _has_album_listen_on_utc_date(
                    session,
                    repository.user.id,
                    existing_album.album_id,
                    candidate.listened_at,
                ):
                    status = "duplicate_listen"
                    candidate.status = status
                    error_message = "Album already has a listen on this UTC date."
                    album_id = None
                else:
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
            import_events.record_candidate_result(
                row, album_id=album_id, status=persisted_status,
                confidence=candidate.confidence, error=error_message,
            )


def _has_album_listen_on_utc_date(
    session: Session,
    user_id: int,
    album_id: int,
    listened_at: str,
) -> bool:
    target_date = _utc_date_key(listened_at)
    if target_date is None:
        return False

    existing_listens = import_events.album_listen_timestamps(session, user_id, album_id)
    return any(_utc_date_key(existing) == target_date for existing in existing_listens)


def _utc_date_key(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parse_timestamp(value).date().isoformat()
    except ValueError:
        return None


def log_candidate_outcomes(candidates: list[AlbumCandidate], *, scope: str) -> None:
    # Candidate outcomes are album sessions, not raw plays or unique albums.
    counts = dict(Counter(candidate.status for candidate in candidates))
    structlog.get_logger(__name__).info(
        "import_candidate_outcomes", candidate_scope=scope,
        album_session_candidates=len(candidates), status_counts=counts,
    )


def summarize_candidates(
    summary: ImportPreviewSummary,
    candidates: list[AlbumCandidate],
) -> None:
    final_album_keys = {
        (
            "id",
            str(candidate.matched_album_id),
        )
        if candidate.matched_album_id is not None
        else (
            "album",
            candidate.artist.strip().casefold(),
            candidate.album.strip().casefold(),
        )
        for candidate in candidates
        if candidate.status in {"matched_existing", "new_album"}
    }
    summary.distinct_album_candidates = len(candidates)
    summary.matched_existing_rows = sum(
        1 for candidate in candidates if candidate.status == "matched_existing"
    )
    summary.new_album_rows = sum(1 for candidate in candidates if candidate.status == "new_album")
    summary.derived_album_listens = summary.matched_existing_rows + summary.new_album_rows
    summary.final_album_count = len(final_album_keys)
    summary.valid_rows = summary.derived_album_listens
    summary.estimated_new_unique_albums = summary.new_album_rows
    summary.review_candidates = sum(
        1 for candidate in candidates if candidate.status == "candidate_review"
    )
    summary.unresolved_rows = summary.review_candidates
    summary.pending_metadata_candidates = sum(
        1 for candidate in candidates if candidate.status in {"no_tracklist", "pending_metadata"}
    )
