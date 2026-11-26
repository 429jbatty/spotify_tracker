"""Source identity, UTC timestamps and the shared listening-session window."""

import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import TypeVar


SPOTIFY_IMPORT_SOURCE = "spotify_import"


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


_Play = TypeVar("_Play")
ALBUM_LISTEN_WINDOW = timedelta(hours=48)


def split_listening_sessions(rows: Iterable[_Play], timestamp: Callable[[_Play], str | None]) -> list[list[_Play]]:
    sessions: list[list[_Play]] = []
    started_at = None
    for row in rows:
        played_at = parse_timestamp(timestamp(row))
        if started_at is None or played_at - started_at > ALBUM_LISTEN_WINDOW:
            sessions.append([])
            started_at = played_at
        sessions[-1].append(row)
    return sessions
