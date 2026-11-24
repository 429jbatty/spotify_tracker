"""Group unresolved import rows and apply the owner’s review decision."""

from typing import Any

from sqlalchemy.orm import Session

from backend.app.database.models import ImportedListeningEvent
from backend.app.database.repositories import (
    import_event_repository as import_events,
    import_session_repository as import_sessions,
)
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.schemas import ImportResolveRequest, ImportReviewItem


def unresolved_review_items(
    session: Session,
    user_id: int,
) -> list[ImportReviewItem]:
    rows = import_events.unresolved_review(session, user_id)

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
    selected = selected[:200]
    session_names = import_sessions.names_for_user_sessions(
        session, user_id,
        {row.import_session_id for row in selected if row.import_session_id is not None},
    )

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
            session_name=session_names.get(row.import_session_id),
        )
        for row in selected
    ]


def resolve_review_item(
    session: Session,
    repository: AlbumLibrary,
    review_item_id: int,
    request: ImportResolveRequest,
) -> dict[str, Any]:
    review_item = import_events.review_item(session, repository.user.id, review_item_id)
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
            album = repository.add_listen(album_id, target.listened_at).record
    else:
        payload = request.create_album.model_dump(exclude={"listened_at"})
        payload.update(source=representative.source, entry_source=representative.source)
        album = repository.add_album(payload, listen_date=representative.listened_at).record
        album_id = album["id"]
        for target in representative_rows[:-1]:
            album = repository.add_listen(album_id, target.listened_at).record

    if representative.rating is not None or representative.notes:
        album = repository.set_feedback(
            album_id,
            rating=representative.rating,
            notes=representative.notes,
        ).record

    for row in target_rows:
        import_events.record_candidate_result(
            row, album_id=album_id, status="resolved", confidence=100, error=None,
        )

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
    repository: AlbumLibrary,
    review_item: ImportedListeningEvent,
) -> list[ImportedListeningEvent]:
    group_key = _review_album_group_key(review_item)
    if review_item.match_status == "candidate_review" and group_key:
        candidates = import_events.review_candidates(session, repository.user.id, review_item.source, review_item.source_user_id)
        target_rows = [
            row for row in candidates if _review_album_group_key(row) == group_key
        ]
    elif review_item.candidate_key:
        target_rows = import_events.rows_for_candidates(session, repository.user.id, [review_item.candidate_key])
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
