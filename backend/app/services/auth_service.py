"""Account authentication and profile-ownership checks.

Sessions are opaque bearer tokens. Only SHA-256 token digests are persisted so a
database disclosure cannot be replayed as an authenticated browser session.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Account, AccountSession, User


def create_account(session: Session, *, email: str, password: str) -> Account:
    normalized_email = _normalize_email(email)
    if session.scalars(select(Account).where(Account.email == normalized_email)).first():
        raise ValueError("An account already exists for this email address.")

    account = Account(
        email=normalized_email,
        password_hash=_hash_password(password),
        created_at=_now(),
    )
    session.add(account)
    session.flush()
    return account


def authenticate_account(session: Session, *, email: str, password: str) -> Account:
    account = session.scalars(
        select(Account).where(Account.email == _normalize_email(email))
    ).first()
    if account is None or not _verify_password(password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return account


def create_session(session: Session, *, account: Account) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AccountSession(
            account_id=account.id,
            token_hash=_token_hash(token),
            created_at=_now(),
        )
    )
    session.flush()
    return token


def require_profile_owner(
    session: Session,
    *,
    user_slug: str,
    authorization: str | None,
) -> User:
    user = session.scalars(select(User).where(User.slug == user_slug.strip().casefold())).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {user_slug}")

    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to manage this profile.",
        )

    account_session = session.scalars(
        select(AccountSession).where(AccountSession.token_hash == _token_hash(token))
    ).first()
    if account_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is invalid or has expired. Sign in again.",
        )
    if user.owner_account_id != account_session.account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this profile.",
        )
    return user


def account_payload(account: Account) -> dict:
    return {
        "email": account.email,
        "profile_slugs": sorted(profile.slug for profile in account.profiles),
    }


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_value: str) -> bool:
    try:
        salt_hex, expected_digest_hex = stored_value.split("$", 1)
        actual_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
        ).hex()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual_digest, expected_digest_hex)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.casefold() == "bearer" and token else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("Enter a valid email address.")
    return normalized


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
