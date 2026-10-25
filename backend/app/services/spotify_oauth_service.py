from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.models import SpotifyOAuthState, User
from backend.app.services.spotify_access_service import require_spotify_sync_access


SCOPES = ["user-read-recently-played"]
OAUTH_STATE_TTL = timedelta(minutes=10)


def authorize_url(session, *, user_id: int, account_id: int) -> str:
    state = secrets.token_urlsafe(32)
    session.add(
        SpotifyOAuthState(
            user_id=user_id,
            account_id=account_id,
            state_hash=_state_hash(state),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    session.flush()
    return _oauth().get_authorize_url(state=state)


def connect_user_from_callback(session, *, code: str, state: str) -> str:
    oauth_state = session.query(SpotifyOAuthState).filter_by(
        state_hash=_state_hash(state)
    ).one_or_none()
    if oauth_state is None:
        raise KeyError("Spotify authorization state is invalid or has expired.")
    created_at = datetime.fromisoformat(oauth_state.created_at)
    if created_at < datetime.now(timezone.utc) - OAUTH_STATE_TTL:
        session.delete(oauth_state)
        session.commit()
        raise KeyError("Spotify authorization state is invalid or has expired.")
    user = session.get(User, oauth_state.user_id)
    if user is None or user.owner_account_id != oauth_state.account_id:
        raise KeyError("Spotify authorization state does not belong to an active profile.")
    try:
        require_spotify_sync_access(user)
    except PermissionError:
        session.delete(oauth_state)
        session.commit()
        raise
    try:
        token_info = _oauth().get_access_token(
            code=code,
            as_dict=True,
            check_cache=False,
        )
    except SpotifyException as exc:
        raise LookupError(_friendly_spotify_error(exc)) from exc

    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        raise LookupError("Spotify did not return a refresh token.")

    spotify = Spotify(auth=token_info["access_token"])
    try:
        spotify_profile = spotify.current_user()
    except SpotifyException as exc:
        raise LookupError(_friendly_spotify_error(exc)) from exc

    SpotifyCredentialsRepository(session).upsert_credentials(
        user_id=user.id,
        refresh_token=refresh_token,
        spotify_user_id=spotify_profile.get("id"),
        scope=token_info.get("scope"),
        connected_at=datetime.now(timezone.utc).isoformat(),
    )
    session.delete(oauth_state)
    session.commit()
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


def _friendly_spotify_error(exc: SpotifyException) -> str:
    message = (getattr(exc, "msg", None) or "").strip()
    status_code = getattr(exc, "http_status", None)
    lowered = message.lower()

    if "not registered for this application" in lowered:
        return (
            "This Spotify account is not allowed to use the app yet. "
            "Add the account under Spotify Developer Dashboard -> Users and Access, "
            "or move the app out of development mode."
        )

    if status_code == 401:
        return "Spotify rejected the authorization token. Please try connecting again."

    if status_code == 403:
        return (
            "Spotify denied access for this account. "
            "Check the app's Spotify Developer Dashboard settings and allowed users."
        )

    if message:
        return f"Spotify authorization failed: {message}"

    return "Spotify authorization failed."


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()
