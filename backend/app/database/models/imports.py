from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from .albums import Album
    from .spotify import SpotifyStreamingEvent
    from .users import User


class ImportSession(Base):
    __tablename__ = "import_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String, index=True)
    source_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="completed", index=True)
    session_name: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str] = mapped_column(String, index=True)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    zip_member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_of_import_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="import_sessions")
    events: Mapped[list["ImportedListeningEvent"]] = relationship(
        back_populates="import_session",
        cascade="all, delete-orphan",
    )
    spotify_streaming_events: Mapped[list["SpotifyStreamingEvent"]] = relationship(
        back_populates="import_session",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list["ImportSessionLog"]] = relationship(
        back_populates="import_session",
        cascade="all, delete-orphan",
    )


class ImportSessionLog(Base):
    __tablename__ = "import_session_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_session_id: Mapped[int] = mapped_column(
        ForeignKey("import_sessions.id"),
        index=True,
    )
    created_at: Mapped[str] = mapped_column(String, index=True)
    level: Mapped[str] = mapped_column(String, default="info", index=True)
    stage: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(String, nullable=True)
    album: Mapped[str | None] = mapped_column(String, nullable=True)
    current: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    import_session: Mapped[ImportSession] = relationship(back_populates="logs")


class ImportedListeningEvent(Base):
    __tablename__ = "imported_listening_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_fingerprint",
            name="uq_imported_event_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    import_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_sessions.id"),
        nullable=True,
        index=True,
    )
    album_id: Mapped[int | None] = mapped_column(ForeignKey("albums.id"), nullable=True)
    source: Mapped[str] = mapped_column(String, index=True)
    source_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_fingerprint: Mapped[str] = mapped_column(String, index=True)
    candidate_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    listened_at: Mapped[str] = mapped_column(String, index=True)
    artist: Mapped[str] = mapped_column(String)
    album: Mapped[str | None] = mapped_column(String, nullable=True)
    track: Mapped[str | None] = mapped_column(String, nullable=True)
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(String, index=True)
    match_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="imported_events")
    import_session: Mapped[ImportSession | None] = relationship(back_populates="events")
    album_ref: Mapped["Album | None"] = relationship()
