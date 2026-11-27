"""Shared SQLite migration locking for application and Alembic entry points."""

import errno
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from weakref import WeakKeyDictionary

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine

from backend.app.config import ROOT_DIR
from backend.app.database.engine import sqlite_file_path

LOCK_TIMEOUT_SECONDS = 60
_engine_locks: WeakKeyDictionary[Engine, Lock] = WeakKeyDictionary()
_engine_locks_guard = Lock()
# Alembic installs process-wide context and operations proxies while it runs.
_alembic_guard = Lock()


@contextmanager
def _file_lock(database: Path) -> Iterator[None]:
    lock_file = database.with_name(f"{database.name}.migration.lock")
    deadline = monotonic() + LOCK_TIMEOUT_SECONDS
    # Retain the lock file so a waiting process always locks the same inode.
    with lock_file.open("a") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timed out waiting for the SQLite migration lock at {lock_file}."
                    ) from exc
                sleep(min(0.1, remaining))
        yield


@contextmanager
def _memory_lock(engine: Engine) -> Iterator[None]:
    with _engine_locks_guard:
        lock = _engine_locks.get(engine)
        if lock is None:
            lock = Lock()
            _engine_locks[engine] = lock
    if not lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise TimeoutError("Timed out waiting for the in-memory SQLite migration lock.")
    try:
        yield
    finally:
        lock.release()


@contextmanager
def migration_connection(engine: Engine) -> Iterator[Connection]:
    database = sqlite_file_path(engine.url)
    lock = _file_lock(database) if database is not None else _memory_lock(engine)
    with lock, engine.connect() as connection:
        yield connection


def alembic_config() -> Config:
    return Config(str(ROOT_DIR / "alembic.ini"))


def upgrade_database(connection: Connection) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    with _alembic_guard:
        command.upgrade(config, "head")
