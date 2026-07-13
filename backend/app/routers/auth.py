from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.schemas import LoginRequest, LoginResponse
from backend.app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _session_factory():
    return sessionmaker(
        bind=get_engine(get_settings().database_url),
        autoflush=False,
        autocommit=False,
    )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    with _session_factory()() as session:
        try:
            account = auth_service.authenticate_account(
                session,
                email=request.email,
                password=request.password,
            )
            token = auth_service.create_session(session, account=account)
            session.commit()
            return LoginResponse(session_token=token, **auth_service.account_payload(account))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
