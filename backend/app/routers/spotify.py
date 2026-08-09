from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.schemas import SpotifyConnectResponse, SpotifyStatus
from backend.app.services import auth_service, spotify_oauth_service
from backend.app.services.spotify_tracking_service import run_tracking_for_user

router = APIRouter(tags=["spotify"])


def _session_factory():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@router.post("/users/{user_slug}/spotify/connect", response_model=SpotifyConnectResponse)
def connect_spotify(
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> SpotifyConnectResponse:
    session_factory = _session_factory()
    with session_factory() as session:
        try:
            user = auth_service.require_profile_owner(
                session,
                user_slug=user_slug,
                authorization=authorization,
            )
            response = SpotifyConnectResponse(
                authorize_url=spotify_oauth_service.authorize_url(
                    session,
                    user_id=user.id,
                    account_id=user.owner_account_id,
                )
            )
            session.commit()
            return response
        except (KeyError, LookupError) as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/users/{user_slug}/spotify/status", response_model=SpotifyStatus)
def spotify_status(
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> SpotifyStatus:
    session_factory = _session_factory()
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
            return SpotifyStatus(connected=False)

        return SpotifyStatus(
            connected=True,
            spotify_user_id=credentials.spotify_user_id,
            connected_at=credentials.connected_at,
            last_successful_sync_at=credentials.last_successful_sync_at,
            last_sync_error=credentials.last_sync_error,
        )


@router.post("/users/{user_slug}/spotify/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_spotify_now(
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    try:
        session_factory = _session_factory()
        with session_factory() as session:
            auth_service.require_profile_owner(
                session,
                user_slug=user_slug,
                authorization=authorization,
            )
        return run_tracking_for_user(user_slug)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/users/{user_slug}/spotify", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_spotify(
    user_slug: str,
    authorization: str | None = Header(default=None),
) -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        user = auth_service.require_profile_owner(
            session,
            user_slug=user_slug,
            authorization=authorization,
        )
        SpotifyCredentialsRepository(session).delete_for_user(user.id)
        session.commit()


@router.get("/spotify/callback")
def spotify_callback(code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spotify callback is missing code or state.",
        )

    session_factory = _session_factory()
    try:
        with session_factory() as session:
            user_slug = spotify_oauth_service.connect_user_from_callback(
                session,
                code=code,
                state=state,
            )
    except (KeyError, LookupError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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
