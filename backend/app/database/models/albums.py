from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from .users import AlbumListen, UserAlbum


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        Index(
            "uq_albums_release_group_mbid",
            "release_group_mbid",
            unique=True,
            sqlite_where=text("release_group_mbid IS NOT NULL AND release_group_mbid != ''"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    artist: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    normalized_identity: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    artist_mbid: Mapped[str | None] = mapped_column(String, nullable=True)
    release_group_mbid: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )
    release_mbid: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, default="unknown")
    entry_source: Mapped[str] = mapped_column(String, default="unknown", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    listens: Mapped[list["AlbumListen"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )
    user_albums: Mapped[list["UserAlbum"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )
    credit_facts: Mapped[list["AlbumCreditFact"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )


class AlbumCreditFact(Base):
    __tablename__ = "album_credit_facts"
    __table_args__ = (
        UniqueConstraint(
            "album_id",
            "person_key",
            "raw_role",
            "source_scope",
            "ingestion_version",
            name="uq_album_credit_fact_identity_role_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), index=True)
    person_key: Mapped[str] = mapped_column(String, index=True)
    person_name: Mapped[str] = mapped_column(String, index=True)
    person_mbid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    identity_resolution: Mapped[str] = mapped_column(String, index=True)
    ingestion_version: Mapped[str] = mapped_column(String, index=True)
    raw_role: Mapped[str] = mapped_column(String, index=True)
    role_bucket: Mapped[str] = mapped_column(String, index=True)
    source_scope: Mapped[str] = mapped_column(String, index=True)
    recording_mbid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    album_track_count: Mapped[int] = mapped_column(Integer, default=0)
    track_share: Mapped[float] = mapped_column(Float, default=0)
    quality_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, index=True)
    updated_at: Mapped[str] = mapped_column(String, index=True)

    album: Mapped[Album] = relationship(back_populates="credit_facts")


class AlbumMetadataCache(Base):
    __tablename__ = "album_metadata_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    artist: Mapped[str] = mapped_column(String)
    album: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="matched", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(String, index=True)
