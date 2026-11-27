from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from .albums import Album
    from .authentication import Account
    from .imports import ImportedListeningEvent, ImportSession
    from .spotify import SpotifyStreamingEvent, UserSpotifyCredentials


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_owner_account_id",
            "owner_account_id",
            unique=True,
            sqlite_where=text("owner_account_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=True,
        index=True,
        unique=True,
    )
    spotify_sync_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )

    owner_account: Mapped["Account | None"] = relationship(back_populates="profiles")

    listens: Mapped[list["AlbumListen"]] = relationship(back_populates="user")
    user_albums: Mapped[list["UserAlbum"]] = relationship(back_populates="user")
    albums_in_progress: Mapped[list["AlbumInProgress"]] = relationship(
        back_populates="user",
    )
    app_state: Mapped[list["UserAppState"]] = relationship(back_populates="user")
    spotify_credentials: Mapped["UserSpotifyCredentials | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    import_sessions: Mapped[list["ImportSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    imported_events: Mapped[list["ImportedListeningEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    spotify_streaming_events: Mapped[list["SpotifyStreamingEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserAlbum(Base):
    __tablename__ = "user_albums"
    __table_args__ = (
        UniqueConstraint("user_id", "album_id", name="uq_user_album"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), index=True)
    your_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="user_albums")
    album: Mapped["Album"] = relationship(back_populates="user_albums")


class AlbumListen(Base):
    __tablename__ = "album_listens"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "album_id",
            "listened_at",
            name="uq_user_album_listen_once",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), index=True)
    listened_at: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="unknown")

    album: Mapped["Album"] = relationship(back_populates="listens")
    user: Mapped[User] = relationship(back_populates="listens")


class AlbumInProgress(Base):
    __tablename__ = "albums_in_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "spotify_album_id",
            name="uq_user_album_in_progress",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    spotify_album_id: Mapped[str] = mapped_column(String, index=True)
    album_name: Mapped[str] = mapped_column(String)
    artist: Mapped[str] = mapped_column(String)
    total_tracks: Mapped[int] = mapped_column(Integer)
    played_tracks: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_played: Mapped[str] = mapped_column(String)
    last_played: Mapped[str] = mapped_column(String)
    completion_logged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    user: Mapped[User] = relationship(back_populates="albums_in_progress")


class UserAppState(Base):
    __tablename__ = "user_app_state"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_app_state_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="app_state")
