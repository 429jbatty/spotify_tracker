from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.schemas import AuthenticatedAccount, GoogleAuthorizeResponse
from backend.app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _session_factory():
    return sessionmaker(bind=get_engine(get_settings().database_url), autoflush=False, autocommit=False)


@router.get("/google/start", response_model=GoogleAuthorizeResponse)
def start_google_sign_in() -> GoogleAuthorizeResponse:
    with _session_factory()() as session:
        url = auth_service.begin_google_sign_in(session, settings=get_settings())
        session.commit()
        return GoogleAuthorizeResponse(authorize_url=url)


@router.get("/me", response_model=AuthenticatedAccount)
def current_account(authorization: str | None = Header(default=None)) -> AuthenticatedAccount:
    with _session_factory()() as session:
        account = auth_service.require_account(session, authorization=authorization)
        return AuthenticatedAccount(**auth_service.account_payload(account))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(default=None)) -> Response:
    with _session_factory()() as session:
        auth_service.revoke_session(session, authorization=authorization)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/google/callback")
def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    settings = get_settings()
    with _session_factory()() as session:
        if error:
            auth_service.cancel_google_sign_in(session, state=state)
            session.commit()
            return _frontend_auth_error_redirect(settings.frontend_origin, "cancelled")
        if not code or not state:
            return _frontend_auth_error_redirect(settings.frontend_origin, "invalid_request")
        try:
            account, session_token = auth_service.complete_google_sign_in(
                session,
                code=code,
                state=state,
                settings=settings,
            )
            session.commit()
        except HTTPException as exc:
            session.commit()
            return _frontend_auth_error_redirect(
                settings.frontend_origin,
                _auth_error_code(exc),
            )
        fragment = urlencode({"session_token": session_token, "email": account.email})
    return RedirectResponse(url=f"{settings.frontend_origin.rstrip('/')}/auth/callback#{fragment}", status_code=status.HTTP_303_SEE_OTHER)


def _frontend_auth_error_redirect(frontend_origin: str, error_code: str) -> RedirectResponse:
    query = urlencode({"auth_error": error_code})
    return RedirectResponse(
        url=f"{frontend_origin.rstrip('/')}/auth/callback?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _auth_error_code(error: HTTPException) -> str:
    if error.status_code == status.HTTP_409_CONFLICT:
        return "identity_conflict"
    if error.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return "unavailable"
    return "invalid_or_expired"
