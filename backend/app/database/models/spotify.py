from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from .imports import ImportSession
    from .users import User


class UserSpotifyCredentials(Base):
    __tablename__ = "user_spotify_credentials"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )
    spotify_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    refresh_token: Mapped[str] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_successful_sync_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="spotify_credentials")


class SpotifyStreamingEvent(Base):
    __tablename__ = "spotify_streaming_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_fingerprint",
            name="uq_spotify_streaming_event_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    import_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_sessions.id"),
        nullable=True,
        index=True,
    )
    event_fingerprint: Mapped[str] = mapped_column(String, index=True)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    source_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    played_at: Mapped[str] = mapped_column(String, index=True)
    ms_played: Mapped[int] = mapped_column(Integer, default=0)
    spotify_track_uri: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    spotify_track_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    spotify_album_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    spotify_album_name: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_album_artist_name: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_album_total_tracks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spotify_album_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    spotify_disc_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spotify_track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spotify_catalog_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    track_name: Mapped[str | None] = mapped_column(String, nullable=True)
    artist_name: Mapped[str | None] = mapped_column(String, nullable=True)
    album_name: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_start: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_end: Mapped[str | None] = mapped_column(String, nullable=True)
    skipped: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    offline: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="spotify_streaming_events")
    import_session: Mapped["ImportSession | None"] = relationship(
        back_populates="spotify_streaming_events"
    )
