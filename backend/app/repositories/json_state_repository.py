import json
from pathlib import Path
from typing import Any


def empty_album_state() -> dict[str, Any]:
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {},
        "most_recently_listened": [],
    }


def _album_identity_from_key(key: str) -> tuple[str, str]:
    artist, separator, album = key.partition(" - ")
    if not separator:
        return "Unknown Artist", key
    return artist or "Unknown Artist", album or "Unknown Album"


def _normalize_completed_albums(completed_albums: dict[str, Any]) -> dict[str, Any]:
    normalized = {}

    for key, record in completed_albums.items():
        if not isinstance(record, dict):
            record = {}

        artist, album = _album_identity_from_key(key)
        normalized[key] = {
            "artist": record.get("artist") or artist,
            "name": record.get("name") or album,
            "source": record.get("source") or "unknown",
            "listen_history": record.get("listen_history") or [],
            **record,
        }

    return normalized


class JsonStateRepository:
    def __init__(self, state_file: str):
        self.state_file = Path(state_file)

    def load_album_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return empty_album_state()

        with self.state_file.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)

        merged_state = {
            **empty_album_state(),
            **state,
        }

        merged_state["completed_albums"] = _normalize_completed_albums(
            merged_state.get("completed_albums", {})
        )

        return merged_state
