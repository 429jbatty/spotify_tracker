from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.schemas import GoogleAuthorizeResponse
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


@router.get("/google/callback")
def google_callback(code: str = Query(), state: str = Query()):
    settings = get_settings()
    with _session_factory()() as session:
        account, session_token = auth_service.complete_google_sign_in(session, code=code, state=state, settings=settings)
        session.commit()
        fragment = urlencode({"session_token": session_token, "email": account.email})
    return RedirectResponse(url=f"{settings.frontend_origin.rstrip('/')}/auth/callback#{fragment}", status_code=status.HTTP_303_SEE_OTHER)
