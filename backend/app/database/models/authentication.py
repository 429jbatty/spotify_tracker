from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .users import User


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    google_subject: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    created_at: Mapped[str] = mapped_column(String, index=True)

    profiles: Mapped[list["User"]] = relationship(back_populates="owner_account")
    sessions: Mapped[list["AccountSession"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    spotify_oauth_states: Mapped[list["SpotifyOAuthState"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)

    account: Mapped[Account] = relationship(back_populates="sessions")


class GoogleOAuthState(Base):
    __tablename__ = "google_oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)


class ProfileOwnershipAssignment(Base):
    __tablename__ = "profile_ownership_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    assigned_at: Mapped[str] = mapped_column(String, index=True)
    assigned_by: Mapped[str] = mapped_column(String, default="operator_cli")


class SpotifyOAuthState(Base):
    __tablename__ = "spotify_oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    state_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)

    account: Mapped[Account] = relationship(back_populates="spotify_oauth_states")
