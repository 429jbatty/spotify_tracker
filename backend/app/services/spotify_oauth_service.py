from datetime import datetime, timezone

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.repositories.user_repository import UserRepository


SCOPES = ["user-read-recently-played"]


def authorize_url(user_slug: str) -> str:
    return _oauth().get_authorize_url(state=user_slug)


def connect_user_from_callback(session, *, code: str, state: str) -> str:
    user = UserRepository(session).require_user_by_slug(state)
    token_info = _oauth().get_access_token(
        code=code,
        as_dict=True,
        check_cache=False,
    )
    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        raise LookupError("Spotify did not return a refresh token.")

    spotify = Spotify(auth=token_info["access_token"])
    spotify_profile = spotify.current_user()
    SpotifyCredentialsRepository(session).upsert_credentials(
        user_id=user.id,
        refresh_token=refresh_token,
        spotify_user_id=spotify_profile.get("id"),
        scope=token_info.get("scope"),
        connected_at=datetime.now(timezone.utc).isoformat(),
    )
    return user.slug


def _oauth() -> SpotifyOAuth:
    return SpotifyOAuth(
        client_id=_required_setting("SPOTIFY_CLIENT_ID"),
        client_secret=_required_setting("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=_required_setting("SPOTIFY_REDIRECT_URI"),
        scope=" ".join(SCOPES),
        show_dialog=True,
        cache_handler=None,
    )


def _required_setting(name: str) -> str:
    import os

    value = os.environ.get(name)
    if not value:
        raise LookupError(f"{name} is not configured.")
    return value
