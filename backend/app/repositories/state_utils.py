from typing import Any


def empty_album_state() -> dict[str, Any]:
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {},
        "most_recently_listened": [],
    }


def _normalize_completed_albums(completed_albums: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, record in completed_albums.items():
        if not isinstance(record, dict):
            record = {}

        artist, album = _split_album_key(key)
        normalized_key = _album_key(record.get("artist") or artist, record.get("name") or album)
        normalized_record = {
            **record,
            "artist": record.get("artist") or artist,
            "name": record.get("name") or album,
            "listen_history": record.get("listen_history") or [],
            "source": record.get("source") or "unknown",
            "entry_source": record.get("entry_source") or record.get("source") or "unknown",
        }
        existing = normalized.get(normalized_key)
        if existing is not None:
            normalized_record["listen_history"] = list(
                dict.fromkeys([
                    *(existing.get("listen_history") or []),
                    *(normalized_record["listen_history"] or []),
                ])
            )
        normalized[normalized_key] = normalized_record

    return normalized


def _split_album_key(key: str) -> tuple[str, str]:
    if " - " not in key:
        return "Unknown Artist", key
    artist, album = key.split(" - ", 1)
    return artist or "Unknown Artist", album or "Unknown Album"


def _album_key(artist: str, album: str) -> str:
    return f"{artist} - {album}"
