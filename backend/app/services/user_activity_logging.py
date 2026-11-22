"""Best-effort events for committed, explicitly manual collection changes."""
from dataclasses import dataclass

import structlog


@dataclass(frozen=True)
class AlbumActivity:
    user_id: int
    profile_slug: str
    album_id: int
    album_artist: str
    album_title: str


def emit_activity(activity: AlbumActivity, events: list[tuple[str, dict]]) -> None:
    """Do not let an observability failure change a committed user action."""
    for event, details in events:
        fields = {
            "user_id": activity.user_id,
            "profile_slug": activity.profile_slug,
            "album_id": activity.album_id,
            "album_artist": activity.album_artist,
            "album_title": activity.album_title,
            "action_source": "manual",
        }
        fields.update(details)
        try:
            structlog.get_logger(__name__).info(event, **fields)
        except Exception:
            # The database is already committed; a logging failure must not turn
            # a successful mutation into an apparent failed request.
            continue
