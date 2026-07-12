from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    album: Mapped[Album] = relationship(back_populates="user_albums")


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

    album: Mapped[Album] = relationship(back_populates="listens")
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


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


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

    user: Mapped[User] = relationship(back_populates="spotify_credentials")


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

    user: Mapped[User] = relationship(back_populates="import_sessions")
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

    user: Mapped[User] = relationship(back_populates="imported_events")
    import_session: Mapped[ImportSession | None] = relationship(back_populates="events")
    album_ref: Mapped[Album | None] = relationship()


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

    user: Mapped[User] = relationship(back_populates="spotify_streaming_events")
    import_session: Mapped[ImportSession | None] = relationship(
        back_populates="spotify_streaming_events"
    )
