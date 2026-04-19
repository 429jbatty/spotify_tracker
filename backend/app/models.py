from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    artist: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
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
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    listens: Mapped[list["AlbumListen"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )


class AlbumListen(Base):
    __tablename__ = "album_listens"
    __table_args__ = (
        UniqueConstraint("album_id", "listened_at", name="uq_album_listen_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), index=True)
    listened_at: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="unknown")

    album: Mapped[Album] = relationship(back_populates="listens")


class AlbumInProgress(Base):
    __tablename__ = "albums_in_progress"

    spotify_album_id: Mapped[str] = mapped_column(String, primary_key=True)
    album_name: Mapped[str] = mapped_column(String)
    artist: Mapped[str] = mapped_column(String)
    total_tracks: Mapped[int] = mapped_column(Integer)
    played_tracks: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_played: Mapped[str] = mapped_column(String)
    last_played: Mapped[str] = mapped_column(String)
    completion_logged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
