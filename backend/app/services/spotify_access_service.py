"""Eligibility rules for Spotify live synchronization."""

from backend.app.models import User


SPOTIFY_SYNC_UNAVAILABLE_MESSAGE = (
    "Spotify sync is currently available only to profiles with existing access."
)


class SpotifySyncAccessUnavailable(PermissionError):
    """Raised when a profile is not entitled to use Spotify live sync."""


def require_spotify_sync_access(user: User) -> None:
    if not user.spotify_sync_enabled:
        raise SpotifySyncAccessUnavailable(SPOTIFY_SYNC_UNAVAILABLE_MESSAGE)
