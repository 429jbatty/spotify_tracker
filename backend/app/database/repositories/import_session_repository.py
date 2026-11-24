from typing import Any, NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.database.models import (
    AlbumListen, ImportedListeningEvent, ImportSession, ImportSessionLog,
    SpotifyStreamingEvent, UserAlbum,
)
from backend.app.database.repositories.album_catalog import AlbumCatalog


_ALBUM_CLEANUP_BATCH_SIZE = 500


class DeletedImportRows(NamedTuple):
    events: int
    listens: int
    memberships: int
    albums: int


def get_for_worker(session: Session, import_session_id: int) -> ImportSession | None:
    return session.get(ImportSession, import_session_id)


def get_for_user(session: Session, user_id: int, import_session_id: int) -> ImportSession | None:
    return session.scalars(
        select(ImportSession).where(
            ImportSession.id == import_session_id,
            ImportSession.user_id == user_id,
        )
    ).first()


def list_for_user(session: Session, user_id: int) -> list[ImportSession]:
    return session.scalars(
        select(ImportSession)
        .where(ImportSession.user_id == user_id)
        .order_by(ImportSession.started_at.desc(), ImportSession.id.desc())
    ).all()


def names_for_user_sessions(
    session: Session, user_id: int, import_session_ids: set[int],
) -> dict[int, str | None]:
    if not import_session_ids:
        return {}
    rows = session.execute(
        select(ImportSession.id, ImportSession.session_name)
        .where(ImportSession.user_id == user_id, ImportSession.id.in_(import_session_ids))
    )
    return {session_id: name for session_id, name in rows}


def logs_for_session(
    session: Session, import_session_id: int, limit: int, order: str,
) -> list[ImportSessionLog]:
    query = select(ImportSessionLog).where(
        ImportSessionLog.import_session_id == import_session_id
    )
    if order == "desc":
        query = query.order_by(ImportSessionLog.created_at.desc(), ImportSessionLog.id.desc())
    else:
        query = query.order_by(ImportSessionLog.created_at.asc(), ImportSessionLog.id.asc())
    return session.scalars(query.limit(limit)).all()


def resumable_ids(session: Session, statuses: set[str]) -> list[int]:
    return session.scalars(
        select(ImportSession.id)
        .where(ImportSession.status.in_(statuses))
        .order_by(ImportSession.started_at.asc(), ImportSession.id.asc())
    ).all()


def delete_session(session: Session, import_session: ImportSession) -> DeletedImportRows:
    imported_rows = session.scalars(
        select(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == import_session.user_id,
        )
    ).all()
    album_ids = list({row.album_id for row in imported_rows if row.album_id is not None})
    listen_keys = {
        (row.album_id, row.listened_at)
        for row in imported_rows
        if row.album_id is not None and row.listened_at
    }

    deleted_listens = 0
    for album_id, listened_at in listen_keys:
        result = session.execute(
            delete(AlbumListen).where(
                AlbumListen.user_id == import_session.user_id,
                AlbumListen.album_id == album_id,
                AlbumListen.listened_at == listened_at,
            )
        )
        deleted_listens += result.rowcount or 0

    deleted_events = len(imported_rows)
    session.execute(
        delete(ImportedListeningEvent).where(
            ImportedListeningEvent.import_session_id == import_session.id,
            ImportedListeningEvent.user_id == import_session.user_id,
        )
    )
    if import_session.source == "spotify_import":
        session.execute(
            delete(SpotifyStreamingEvent).where(
                SpotifyStreamingEvent.import_session_id == import_session.id,
                SpotifyStreamingEvent.user_id == import_session.user_id,
            )
        )
    session.delete(import_session)
    session.flush()

    removed_memberships = 0
    deleted_albums = 0
    catalog = AlbumCatalog(session)
    for start in range(0, len(album_ids), _ALBUM_CLEANUP_BATCH_SIZE):
        batch = album_ids[start : start + _ALBUM_CLEANUP_BATCH_SIZE]
        membership_delete = delete(UserAlbum).where(
            UserAlbum.user_id == import_session.user_id,
            UserAlbum.album_id.in_(batch),
            ~select(AlbumListen.id).where(
                AlbumListen.user_id == UserAlbum.user_id,
                AlbumListen.album_id == UserAlbum.album_id,
            ).exists(),
        )
        result = session.execute(membership_delete.execution_options(synchronize_session="fetch"))
        removed_memberships += result.rowcount or 0
        deleted_albums += catalog.delete_albums_without_listens_or_memberships(batch)
    return DeletedImportRows(deleted_events, deleted_listens, removed_memberships, deleted_albums)


def duplicate_spotify_session(session: Session, user_id: int, file_sha256: str) -> int | None:
    return session.scalar(
        select(ImportSession.id)
        .where(
            ImportSession.user_id == user_id,
            ImportSession.source == "spotify_import",
            ImportSession.file_sha256 == file_sha256,
            ImportSession.status == "completed",
        )
        .order_by(ImportSession.started_at.desc(), ImportSession.id.desc())
        .limit(1)
    )


def stage_session(session: Session, **values: Any) -> ImportSession:
    import_session = ImportSession(**values)
    session.add(import_session)
    session.flush()
    return import_session


def stage_log(session: Session, **values: Any) -> None:
    session.add(ImportSessionLog(**values))


def finish_session(import_session: ImportSession, status: str, completed_at: str) -> None:
    import_session.status = status
    import_session.completed_at = completed_at
