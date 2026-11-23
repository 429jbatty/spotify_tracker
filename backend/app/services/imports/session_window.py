"""Partition ordered plays into sessions anchored on the first play’s UTC timestamp."""

from collections.abc import Callable, Iterable
from datetime import timedelta
from typing import TypeVar

from .common import parse_timestamp


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
