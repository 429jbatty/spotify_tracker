"""Google-backed account authentication and profile-ownership checks."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import HTTPException, status
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import Account, User
from backend.app.repositories.account_repository import AccountRepository

logger = structlog.get_logger(__name__)

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_STATE_TTL = timedelta(minutes=10)


def begin_google_sign_in(session: Session, *, settings: Settings) -> str:
    _require_google_settings(settings)
    state = secrets.token_urlsafe(32)
    AccountRepository(session).begin_google_sign_in(_token_hash(state), _now())
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode({'client_id': settings.google_client_id, 'redirect_uri': settings.google_redirect_uri, 'response_type': 'code', 'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})}"


def complete_google_sign_in(session: Session, *, code: str, state: str, settings: Settings) -> tuple[Account, str]:
    _require_google_settings(settings)
    repository = AccountRepository(session)
    created_at = repository.take_google_state(_token_hash(state))
    if created_at is None or _is_expired(created_at):
        if created_at is not None:
            session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in request is invalid or expired. Try again.")
    try:
        token_response = httpx.post(GOOGLE_TOKEN_ENDPOINT, data={"code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code"}, timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is temporarily unavailable. Try again.",
        ) from exc
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
    account = repository.find_by_subject(subject)
    if account is None:
        normalized_email = _normalize_email(email)
        account = repository.find_by_email(normalized_email)
        if account is not None:
            if account.google_subject is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This Google email belongs to a different account identity.")
            repository.link_google_subject(account, subject)
        else:
            account = repository.create_account(
                email=normalized_email, google_subject=subject,
                password_hash=_disabled_password_marker(), created_at=_now(),
            )
    return account, create_session(session, account=account)


def cancel_google_sign_in(session: Session, *, state: str | None) -> None:
    """Consume a pending OAuth state when Google returns a denial callback."""
    if state:
        AccountRepository(session).discard_google_state(_token_hash(state))


def create_session(session: Session, *, account: Account) -> str:
    token = secrets.token_urlsafe(32)
    AccountRepository(session).record_session(account_id=account.id, token_hash=_token_hash(token), created_at=_now())
    return token


def create_account(session: Session, *, email: str, password: str) -> Account:
    """Compatibility helper for tests and data fixtures; it is not an auth flow.

    Production accounts are created exclusively by :func:`complete_google_sign_in`.
    """
    repository = AccountRepository(session)
    normalized_email = _normalize_email(email)
    if repository.find_by_email(normalized_email):
        raise ValueError("An account already exists for this email address.")
    return repository.create_account(
        email=normalized_email, google_subject=f"fixture:{secrets.token_urlsafe(16)}",
        password_hash=_disabled_password_marker(), created_at=_now(),
    )


def require_account(session: Session, *, authorization: str | None) -> Account:
    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    account = AccountRepository(session).account_for_token(_token_hash(token))
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is invalid or has expired. Sign in again.")
    return account


def revoke_session(session: Session, *, authorization: str | None) -> None:
    """Invalidate the account session represented by the supplied bearer token."""
    token = _bearer_token(authorization)
    if token is not None:
        AccountRepository(session).revoke_session(_token_hash(token))


def require_profile_owner(session: Session, *, user_slug: str, authorization: str | None) -> User:
    repository = AccountRepository(session)
    user = repository.find_profile(user_slug.strip().casefold())
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {user_slug}")
    account = require_account(session, authorization=authorization)
    if user.owner_account_id != account.id:
        logger.warning("profile_access_denied", user_id=user.id, actor_account_id=account.id, reason="not_owner")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this profile.")
    return user


def require_profile_creation_eligibility(session: Session, *, account: Account) -> None:
    if AccountRepository(session).owned_profile(account.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Google account already owns a profile.",
        )


def create_owned_profile(
    session: Session, *, account: Account, slug: str, display_name: str,
) -> tuple[User, str]:
    require_profile_creation_eligibility(session, account=account)
    token = secrets.token_urlsafe(32)
    user = AccountRepository(session).create_owned_profile(
        slug=slug, display_name=display_name, account_id=account.id,
        token_hash=_token_hash(token), created_at=_now(),
    )
    return user, token


def _require_account_without_other_profile(repository: AccountRepository, *, account: Account, user: User) -> None:
    existing_profile = repository.owned_profile(account.id)
    if existing_profile is not None and existing_profile.id != user.id:
        raise ValueError(
            f"Account {account.email} already owns profile {existing_profile.slug}."
        )


def bind_profile_owner(session: Session, *, user_slug: str, account_email: str, assigned_by: str = "operator_cli") -> User:
    repository = AccountRepository(session)
    user = repository.find_profile(user_slug.strip().casefold())
    account = repository.find_by_email(_normalize_email(account_email))
    if user is None:
        raise ValueError(f"Profile not found: {user_slug}")
    if account is None or not account.google_subject:
        raise ValueError("Account not found or has not signed in with Google yet.")
    if user.owner_account_id is not None and user.owner_account_id != account.id:
        raise ValueError(f"Profile {user.slug} is already assigned to another account.")
    if user.owner_account_id == account.id:
        return user
    _require_account_without_other_profile(repository, account=account, user=user)
    repository.assign_profile_owner(user=user, account=account, assigned_at=_now(), assigned_by=assigned_by)
    return user


def unbind_profile_owner(session: Session, *, user_slug: str) -> User:
    """Remove a profile's current owner without deleting its account or history.

    This is intentionally idempotent so operators can reset a development
    profile before repeating ownership-flow tests.
    """
    repository = AccountRepository(session)
    user = repository.find_profile(user_slug.strip().casefold())
    if user is None:
        raise ValueError(f"Profile not found: {user_slug}")
    if user.owner_account_id is None:
        return user
    repository.remove_profile_owner(user)
    return user


def prebind_profile_owner(session: Session, *, user_slug: str, account_email: str) -> User:
    """Pre-authorize a verified Google email to claim an existing profile.

    The Google subject is deliberately stored only after that email completes
    its first verified Google sign-in.
    """
    repository = AccountRepository(session)
    user = repository.find_profile(user_slug.strip().casefold())
    if user is None:
        raise ValueError(f"Profile not found: {user_slug}")

    normalized_email = _normalize_email(account_email)
    if user.owner_account_id is not None:
        current_account = repository.find_by_id(user.owner_account_id)
        if current_account is not None and current_account.email == normalized_email:
            return user
        raise ValueError(f"Profile {user.slug} is already assigned to another account.")

    account = repository.find_by_email(normalized_email)
    if account is None:
        account = repository.create_account(
            email=normalized_email, password_hash=_disabled_password_marker(), created_at=_now(),
        )

    _require_account_without_other_profile(repository, account=account, user=user)
    repository.assign_profile_owner(user=user, account=account, assigned_at=_now(), assigned_by="operator_prebind")
    return user


def account_payload(session: Session, account: Account) -> dict:
    profiles = AccountRepository(session).profile_names_for_account(account.id)
    return {
        "email": account.email,
        "profile_slugs": [slug for slug, _ in profiles],
        "profiles": [
            {"slug": slug, "display_name": display_name}
            for slug, display_name in profiles
        ],
    }


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
