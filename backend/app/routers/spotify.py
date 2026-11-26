from urllib.parse import urlencode

import structlog

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import RedirectResponse

from backend.app.config import get_settings
from backend.app.dependencies import AppSessions
from backend.app.database.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.schemas import SpotifyConnectResponse, SpotifyStatus
from backend.app.services import (
    auth_service,
    spotify_access_service,
    spotify_oauth_service,
)
from backend.app.services.spotify_tracking_service import run_tracking_for_user

router = APIRouter(tags=["spotify"])
logger = structlog.get_logger(__name__)


@router.post("/users/{user_slug}/spotify/connect", response_model=SpotifyConnectResponse)
def connect_spotify(
    session_factory: AppSessions,
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> SpotifyConnectResponse:
    with session_factory() as session:
        try:
            user = auth_service.require_profile_owner(
                session,
                user_slug=user_slug,
                authorization=authorization,
            )
            spotify_access_service.require_spotify_sync_access(user)
            response = SpotifyConnectResponse(
                authorize_url=spotify_oauth_service.authorize_url(
                    session,
                    user_id=user.id,
                    account_id=user.owner_account_id,
                )
            )
            return response
        except (KeyError, LookupError) as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except spotify_access_service.SpotifySyncAccessUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/users/{user_slug}/spotify/status", response_model=SpotifyStatus)
def spotify_status(
    session_factory: AppSessions,
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> SpotifyStatus:
    with session_factory() as session:
        try:
            user = auth_service.require_profile_owner(
                session,
                user_slug=user_slug,
                authorization=authorization,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

        credentials = SpotifyCredentialsRepository(session).get_for_user(user.id)
        if credentials is None:
            return SpotifyStatus(
                connected=False,
                spotify_sync_eligible=user.spotify_sync_enabled,
            )

        return SpotifyStatus(
            connected=True,
            spotify_sync_eligible=user.spotify_sync_enabled,
            spotify_user_id=credentials.spotify_user_id,
            connected_at=credentials.connected_at,
            last_successful_sync_at=credentials.last_successful_sync_at,
            last_sync_error=credentials.last_sync_error,
        )


@router.post("/users/{user_slug}/spotify/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_spotify_now(
    session_factory: AppSessions,
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    try:
        with session_factory() as session:
            user = auth_service.require_profile_owner(
                session,
                user_slug=user_slug,
                authorization=authorization,
            )
            spotify_access_service.require_spotify_sync_access(user)
        return run_tracking_for_user(user_slug, open_session=session_factory)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except spotify_access_service.SpotifySyncAccessUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/users/{user_slug}/spotify", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_spotify(
    session_factory: AppSessions,
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> None:
    with session_factory() as session:
        user = auth_service.require_profile_owner(
            session,
            user_slug=user_slug,
            authorization=authorization,
        )
        SpotifyCredentialsRepository(session).delete_for_user(user.id)


@router.get("/spotify/callback")
def spotify_callback(session_factory: AppSessions, code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or not state:
        logger.warning("spotify_connection_failed", reason="invalid_request")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spotify callback is missing code or state.",
        )

    try:
        with session_factory() as session:
            user_slug = spotify_oauth_service.connect_user_from_callback(
                session,
                code=code,
                state=state,
            )
    except (KeyError, LookupError) as exc:
        logger.warning("spotify_connection_failed", reason="invalid_state" if isinstance(exc, KeyError) else "provider_unavailable")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except spotify_access_service.SpotifySyncAccessUnavailable as exc:
        logger.warning("spotify_connection_failed", reason="access_denied")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    redirect_url = _frontend_redirect(
        {
            "spotify": "connected",
            "user": user_slug,
        }
    )
    return RedirectResponse(redirect_url)


def _frontend_redirect(params: dict[str, str]) -> str:
    settings = get_settings()
    return f"{settings.frontend_origin}/?{urlencode(params)}"
