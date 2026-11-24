"""Normalize album input and format persisted catalog records."""

import json
from typing import Any

from backend.app.user_tags import normalize_user_tags


CATALOG_RECORD_FIELDS = (
    "id", "album_key", "artist", "name", "artist_mbid", "release_group_mbid",
    "release_mbid", "label", "release_year", "release_month", "release_day",
    "image_url", "remote_image_url", "local_image_path", "source", "entry_source",
)


def album_display_key(artist: str, title: str) -> str:
    return f"{artist} - {title}"


def normalize_album_record(
    record: Any, key: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(record, dict):
        record = {}
    if key is None:
        key = album_display_key(record.get("artist", ""), record.get("name", ""))

    if " - " in key:
        artist, title = key.split(" - ", 1)
        artist, title = artist or "Unknown Artist", title or "Unknown Album"
    else:
        artist, title = "Unknown Artist", key

    artist = record.get("artist") or artist
    title = record.get("name") or title
    return album_display_key(artist, title), {
        **record,
        "artist": artist,
        "name": title,
        "listen_history": record.get("listen_history") or [],
        "source": record.get("source") or "unknown",
        "entry_source": record.get("entry_source") or record.get("source") or "unknown",
    }


def normalize_completed_albums(completed_albums: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, record in completed_albums.items():
        display_key, record = normalize_album_record(record, key)
        existing = normalized.get(display_key)
        if existing is not None:
            record["listen_history"] = list(dict.fromkeys([
                *existing["listen_history"], *record["listen_history"],
            ]))
        normalized[display_key] = record
    return normalized


def normalize_entry_source(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    legacy_sources = {
        "csv": "csv_upload",
        "lastfm": "lastfm_import",
        "spotify_export": "spotify_export_upload",
        "musicbrainz": "spotify_sync",
    }
    return legacy_sources.get(normalized, normalized) or "unknown"


def stored_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {
            "id", "album_key", "listen_history", "your_tags", "remote_image_url",
            "local_image_path", "entry_source", "normalized_identity", "rating", "notes",
        }
    }


def read_metadata(album) -> dict[str, Any]:
    metadata = getattr(album, "metadata_json", None)
    if isinstance(metadata, dict):
        return metadata

    blob = getattr(album, "metadata_json_blob", None)
    if blob is None:
        return {}
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    try:
        parsed = json.loads(blob.decode("utf-8") if isinstance(blob, bytes) else str(blob))
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def catalog_record(album) -> dict[str, Any]:
    return {
        **{
            key: value
            for key, value in read_metadata(album).items()
            if key not in {"_manual_input_identity", "listen_history", "your_tags", "rating", "notes"}
        },
        **{key: getattr(album, key) for key in CATALOG_RECORD_FIELDS},
    }


def display_record(album) -> dict[str, Any]:
    record = catalog_record(album)
    if album.local_image_path:
        filename = album.local_image_path.removeprefix("artwork/").lstrip("/")
        record["image_url"] = f"/media/artwork/{filename}"
    return record


def library_record(album, membership, listen_history: list[str]) -> dict[str, Any]:
    return {
        **display_record(album),
        "listen_history": listen_history,
        "your_tags": normalize_user_tags(membership.your_tags if membership else []),
        "rating": membership.rating if membership else None,
        "notes": membership.notes if membership else None,
    }
