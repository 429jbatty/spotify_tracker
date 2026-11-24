"""Apply album-session decisions to the library, import rows and summary."""

from collections import Counter, defaultdict

import structlog
from sqlalchemy.orm import Session

from backend.app.database.models import ImportedListeningEvent
from backend.app.database.repositories import import_event_repository as import_events
from backend.app.database.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportPreviewSummary

from .events import parse_timestamp
from .matching import AlbumCandidate
from .metadata import ExistingAlbumMatch, album_match_key, load_existing_albums


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

        album_id, error_message = _apply_listen(session, repository, album_index, candidate)
        persisted_status = {
            "matched_existing": "processed_album_listen",
            "new_album": "processed_album_listen",
            "no_tracklist": "pending_metadata",
        }.get(candidate.status, candidate.status)
        for row in candidate_rows:
            import_events.record_candidate_result(
                row, album_id=album_id, status=persisted_status,
                confidence=candidate.confidence, error=error_message,
            )


def _apply_listen(session, repository, album_index, candidate):
    if candidate.status == "new_album":
        # Completion of a new album always requires a matched metadata tracklist.
        record = candidate.metadata
        key = album_match_key(record.get("artist"), record.get("name"))
        existing = album_index.get(key)
        if existing is None:
            created = repository.create_completed_album(record, listen_date=candidate.listened_at)
            album_index[key] = ExistingAlbumMatch(created["id"], created)
            return created["id"], candidate.status_detail
        album_id = existing.album_id
    elif candidate.status == "matched_existing":
        album_id = candidate.matched_album_id
    else:
        return None, candidate.status_detail

    if _has_album_listen_on_utc_date(session, repository.user.id, album_id, candidate.listened_at):
        candidate.status = "duplicate_listen"
        return None, "Album already has a listen on this UTC date."
    repository.add_album_listen(album_id, candidate.listened_at)
    return album_id, candidate.status_detail


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
    counts = Counter(candidate.status for candidate in candidates)
    albums = {
        candidate.matched_album_id if candidate.matched_album_id is not None
        else album_match_key(candidate.artist, candidate.album)
        for candidate in candidates if candidate.status in {"matched_existing", "new_album"}
    }
    summary.distinct_album_candidates = len(candidates)
    summary.matched_existing_rows = counts["matched_existing"]
    summary.new_album_rows = summary.estimated_new_unique_albums = counts["new_album"]
    summary.valid_rows = summary.derived_album_listens = counts["matched_existing"] + counts["new_album"]
    summary.final_album_count = len(albums)
    summary.unresolved_rows = summary.review_candidates = counts["candidate_review"]
    summary.pending_metadata_candidates = counts["no_tracklist"] + counts["pending_metadata"]
