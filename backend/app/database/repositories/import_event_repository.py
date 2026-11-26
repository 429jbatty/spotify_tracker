from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.database.models import ImportedListeningEvent


SPOTIFY_CANDIDATE_INSERT_BATCH_SIZE = 500
_CANDIDATE_LOOKUP_BATCH_SIZE = 500


def diagnostic_candidates(
    session: Session, user_id: int, import_session_id: int, artist: str, album: str,
) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.user_id == user_id,
            func.lower(ImportedListeningEvent.artist) == artist,
            func.lower(func.coalesce(ImportedListeningEvent.album, "")) == album,
        )
    ).all()


def unresolved_review(session: Session, user_id: int) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.match_status.in_(("candidate_review", "unresolved", "failed")),
        )
        .order_by(ImportedListeningEvent.listened_at.desc(), ImportedListeningEvent.id.desc())
        .limit(1000)
    ).all()


def review_item(session: Session, user_id: int, review_item_id: int) -> ImportedListeningEvent | None:
    return session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.id == review_item_id,
        )
    ).first()


def review_candidates(
    session: Session, user_id: int, source: str, source_user_id: str | None,
) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.source == source,
            ImportedListeningEvent.source_user_id == source_user_id,
            ImportedListeningEvent.match_status == "candidate_review",
        )
    ).all()


def pending_metadata(
    session: Session, user_id: int, import_session_id: int,
) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.match_status == "pending_metadata",
        )
    ).all()


def session_event_count(session: Session, user_id: int, import_session_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.user_id == user_id,
        )
    ) or 0


def raw_spotify_candidates(
    session: Session, user_id: int, import_session_id: int,
) -> list[ImportedListeningEvent]:
    return session.scalars(
        select(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.source == "spotify_import",
            ImportedListeningEvent.match_status == "raw_imported",
        )
        .order_by(ImportedListeningEvent.listened_at, ImportedListeningEvent.id)
    ).all()


def count_spotify_candidates(session: Session, user_id: int, import_session_id: int, status: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(ImportedListeningEvent)
        .where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.source == "spotify_import",
            ImportedListeningEvent.match_status == status,
        )
    ) or 0


def rows_for_candidates(
    session: Session, user_id: int, candidate_keys: list[str],
) -> list[ImportedListeningEvent]:
    """Load a profile's candidate events across import sessions in bounded batches."""
    keys = list(dict.fromkeys(candidate_keys))
    rows = []
    for start in range(0, len(keys), _CANDIDATE_LOOKUP_BATCH_SIZE):
        batch = keys[start : start + _CANDIDATE_LOOKUP_BATCH_SIZE]
        rows.extend(session.scalars(
            select(ImportedListeningEvent).where(
                ImportedListeningEvent.user_id == user_id,
                ImportedListeningEvent.candidate_key.in_(batch),
            )
        ).all())
    return rows


def latest_timestamp(
    session: Session, user_id: int, source: str, source_user_id: str | None = None,
) -> str | None:
    query = select(func.max(ImportedListeningEvent.listened_at)).where(
        ImportedListeningEvent.user_id == user_id,
        ImportedListeningEvent.source == source,
    )
    if source_user_id:
        query = query.where(ImportedListeningEvent.source_user_id == source_user_id)
    return session.scalar(query)


def has_fingerprint(session: Session, user_id: int, fingerprint: str) -> bool:
    return session.scalars(
        select(ImportedListeningEvent.id).where(
            ImportedListeningEvent.user_id == user_id,
            ImportedListeningEvent.event_fingerprint == fingerprint,
        )
    ).first() is not None


def stage_lastfm_event(session: Session, **values: Any) -> ImportedListeningEvent:
    event = ImportedListeningEvent(**values)
    session.add(event)
    return event


def insert_spotify_candidates(session: Session, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), SPOTIFY_CANDIDATE_INSERT_BATCH_SIZE):
        batch = rows[start : start + SPOTIFY_CANDIDATE_INSERT_BATCH_SIZE]
        statement = sqlite_insert(ImportedListeningEvent).values(batch)
        session.execute(statement.on_conflict_do_nothing(index_elements=["user_id", "event_fingerprint"]))
    session.flush()


def record_candidate_result(
    event: ImportedListeningEvent, *, album_id: int | None, status: str,
    confidence: int | None, error: str | None,
) -> None:
    event.album_id = album_id
    event.match_status = status
    event.match_confidence = confidence
    event.error_message = error


def linked_album_ids(session: Session, import_session_id: int) -> list[int]:
    return list(session.scalars(
        select(ImportedListeningEvent.album_id)
        .where(
            ImportedListeningEvent.import_session_id == import_session_id,
            ImportedListeningEvent.album_id.is_not(None),
        )
        .distinct()
        .order_by(ImportedListeningEvent.album_id)
    ))
