"""Google-backed account authentication and profile-ownership checks."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import Account, AccountSession, GoogleOAuthState, ProfileOwnershipAssignment, User

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_STATE_TTL = timedelta(minutes=10)


def begin_google_sign_in(session: Session, *, settings: Settings) -> str:
    _require_google_settings(settings)
    state = secrets.token_urlsafe(32)
    session.add(GoogleOAuthState(state_hash=_token_hash(state), created_at=_now()))
    session.flush()
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode({'client_id': settings.google_client_id, 'redirect_uri': settings.google_redirect_uri, 'response_type': 'code', 'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})}"


def complete_google_sign_in(session: Session, *, code: str, state: str, settings: Settings) -> tuple[Account, str]:
    _require_google_settings(settings)
    oauth_state = session.scalars(select(GoogleOAuthState).where(GoogleOAuthState.state_hash == _token_hash(state))).first()
    if oauth_state is None or _is_expired(oauth_state.created_at):
        if oauth_state is not None:
            session.delete(oauth_state)
            session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in request is invalid or expired. Try again.")
    session.delete(oauth_state)
    token_response = httpx.post(GOOGLE_TOKEN_ENDPOINT, data={"code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code"}, timeout=10)
    if token_response.is_error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google could not complete sign-in. Try again.")
    try:
        claims = id_token.verify_oauth2_token(token_response.json().get("id_token"), GoogleRequest(), settings.google_client_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google returned an invalid identity token.") from exc
    subject = claims.get("sub")
    email = claims.get("email")
    if not subject or not email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google did not return a verified account identity.")
    account = session.scalars(select(Account).where(Account.google_subject == subject)).first()
    if account is None:
        if session.scalars(select(Account).where(Account.email == _normalize_email(email))).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This Google email belongs to an existing account and must be linked by an operator.")
        account = Account(email=_normalize_email(email), google_subject=subject, password_hash=_disabled_password_marker(), created_at=_now())
        session.add(account)
        session.flush()
    return account, create_session(session, account=account)


def create_session(session: Session, *, account: Account) -> str:
    token = secrets.token_urlsafe(32)
    session.add(AccountSession(account_id=account.id, token_hash=_token_hash(token), created_at=_now()))
    session.flush()
    return token


def create_account(session: Session, *, email: str, password: str) -> Account:
    """Compatibility helper for tests and data fixtures; it is not an auth flow.

    Production accounts are created exclusively by :func:`complete_google_sign_in`.
    """
    normalized_email = _normalize_email(email)
    if session.scalars(select(Account).where(Account.email == normalized_email)).first():
        raise ValueError("An account already exists for this email address.")
    account = Account(email=normalized_email, google_subject=f"fixture:{secrets.token_urlsafe(16)}", password_hash=_disabled_password_marker(), created_at=_now())
    session.add(account)
    session.flush()
    return account


def require_account(session: Session, *, authorization: str | None) -> Account:
    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    account_session = session.scalars(select(AccountSession).where(AccountSession.token_hash == _token_hash(token))).first()
    if account_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is invalid or has expired. Sign in again.")
    return account_session.account


def require_profile_owner(session: Session, *, user_slug: str, authorization: str | None) -> User:
    user = session.scalars(select(User).where(User.slug == user_slug.strip().casefold())).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {user_slug}")
    if user.owner_account_id != require_account(session, authorization=authorization).id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this profile.")
    return user


def bind_profile_owner(session: Session, *, user_slug: str, account_email: str, assigned_by: str = "operator_cli") -> User:
    user = session.scalars(select(User).where(User.slug == user_slug.strip().casefold())).first()
    account = session.scalars(select(Account).where(Account.email == _normalize_email(account_email))).first()
    if user is None:
        raise ValueError(f"Profile not found: {user_slug}")
    if account is None or not account.google_subject:
        raise ValueError("Account not found or has not signed in with Google yet.")
    if user.owner_account_id is not None and user.owner_account_id != account.id:
        raise ValueError(f"Profile {user.slug} is already assigned to another account.")
    user.owner_account_id = account.id
    session.add(ProfileOwnershipAssignment(user_id=user.id, account_id=account.id, assigned_at=_now(), assigned_by=assigned_by))
    session.commit()
    return user


def account_payload(account: Account) -> dict:
    return {"email": account.email, "profile_slugs": sorted(profile.slug for profile in account.profiles)}


def _require_google_settings(settings: Settings) -> None:
    if not all((settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri)):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured yet.")


def _is_expired(created_at: str) -> bool:
    return datetime.fromisoformat(created_at) + GOOGLE_STATE_TTL < datetime.now(timezone.utc)


def _disabled_password_marker() -> str:
    return f"google-only${secrets.token_urlsafe(24)}"


def _bearer_token(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    return token if scheme.casefold() == "bearer" and token else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("Google did not return a valid email address.")
    return normalized


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
