from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class NormalizedImportEvent:
    listened_at: str | None
    artist: str | None
    album: str | None
    track: str | None
    source: str
    source_user_id: str | None
    source_event_id: str | None
    source_label: str | None
    rating: int | None
    notes: str | None
    raw_payload: dict[str, Any]


@dataclass
class NormalizedSpotifyStreamingEvent:
    played_at: str | None
    ms_played: int
    spotify_track_uri: str | None
    track_name: str | None
    artist_name: str | None
    album_name: str | None
    platform: str | None
    country: str | None
    reason_start: str | None
    reason_end: str | None
    skipped: bool | None
    offline: bool | None
    raw_payload: dict[str, Any]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc).isoformat()
    if len(text) == 16 and " " in text:
        return (
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            .replace(tzinfo=timezone.utc)
            .isoformat()
        )
    if text.endswith("Z"):
        return text
    try:
        return (
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat()
        )
    except ValueError:
        return text


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def normalize_spotify_streaming_event(row: dict[str, Any]) -> NormalizedSpotifyStreamingEvent:
    return NormalizedSpotifyStreamingEvent(
        played_at=normalize_timestamp(row.get("ts") or row.get("endTime")),
        ms_played=parse_int(row.get("ms_played") or row.get("msPlayed")) or 0,
        spotify_track_uri=clean_text(row.get("spotify_track_uri")),
        track_name=clean_text(
            row.get("master_metadata_track_name") or row.get("trackName")
        ),
        artist_name=clean_text(
            row.get("master_metadata_album_artist_name") or row.get("artistName")
        ),
        album_name=clean_text(row.get("master_metadata_album_album_name")),
        platform=clean_text(row.get("platform")),
        country=clean_text(row.get("conn_country") or row.get("country")),
        reason_start=clean_text(row.get("reason_start")),
        reason_end=clean_text(row.get("reason_end")),
        skipped=_parse_bool(row.get("skipped")),
        offline=_parse_bool(row.get("offline")),
        raw_payload=row,
    )


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
