"""Classify database failures without recording SQL, parameters, or paths."""
from pathlib import Path
import sqlite3
import traceback

from sqlalchemy.exc import SQLAlchemyError, StatementError


def database_error_fields(exc: Exception) -> dict:
    if not isinstance(exc, SQLAlchemyError):
        return {}
    statement = exc.statement if isinstance(exc, StatementError) else None
    verb = statement.lstrip().split(None, 1)[0].upper() if statement and statement.strip() else ""
    operation = "write" if verb in {"INSERT", "UPDATE", "DELETE", "REPLACE"} else "read" if verb == "SELECT" else "unknown"
    fields = {"database_error_type": type(exc).__name__, "database_operation": operation}
    original = getattr(exc, "orig", None)
    if isinstance(original, sqlite3.Error):
        code = getattr(original, "sqlite_errorcode", None)
        if isinstance(code, int):
            fields["sqlite_error_code"] = code
        name = getattr(original, "sqlite_errorname", None)
        if isinstance(name, str) and name.startswith("SQLITE_"):
            fields["sqlite_error_name"] = name
        # DB-API error messages may contain user data; emit only known categories.
        message = str(original).casefold()
        for text, category in (
            ("database is locked", "locked"),
            ("database table is locked", "locked"),
            ("database or disk is full", "disk_full"),
            ("readonly database", "read_only"),
            ("unable to open database file", "open_failed"),
            ("no such table", "missing_table"),
            ("no such column", "missing_column"),
            ("constraint failed", "constraint"),
        ):
            if text in message:
                fields["database_reason"] = category
                break
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    application_frames = [frame for frame in frames if "/site-packages/" not in frame.filename and "/lib/python" not in frame.filename]
    if application_frames:
        frame = application_frames[-1]
        fields["database_location"] = f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
    return fields
