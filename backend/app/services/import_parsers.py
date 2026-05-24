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
