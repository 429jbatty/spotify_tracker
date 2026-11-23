"""User-scoped import history, activity logs and deletion."""

from sqlalchemy.orm import Session

from backend.app.repositories import import_session_repository as import_sessions
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ImportDeleteResponse, ImportSessionLogEntry, ImportSessionSummary

from .progress import TERMINAL_IMPORT_STATUSES, build_import_session_summary


def import_history(
    session: Session,
    repository: SqliteStateRepository,
) -> list[ImportSessionSummary]:
    rows = import_sessions.list_for_user(session, repository.user.id)
    return [build_import_session_summary(row) for row in rows]


def import_session_logs(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
    *,
    limit: int = 100,
    order: str = "asc",
) -> list[ImportSessionLogEntry]:
    import_session = import_sessions.get_for_user(session, repository.user.id, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")

    safe_limit = max(1, min(limit, 500))
    rows = import_sessions.logs_for_session(session, import_session.id, safe_limit, order)
    return [ImportSessionLogEntry(**vars(row), metadata=row.metadata_json or {}) for row in rows]


def delete_import_session(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
) -> ImportDeleteResponse:
    import_session = import_sessions.get_for_user(session, repository.user.id, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")
    if import_session.status not in TERMINAL_IMPORT_STATUSES:
        raise ValueError("Cannot delete an import while it is still running.")

    deleted = import_sessions.delete_session(session, import_session)
    session.commit()
    return ImportDeleteResponse(
        import_session_id=import_session_id,
        deleted_events=deleted.events,
        deleted_listens=deleted.listens,
        removed_user_albums=deleted.memberships,
        deleted_albums=deleted.albums,
    )
