import json

from sqlalchemy import Engine, select, text

DEFAULT_USER_SLUG = "jacob"
DEFAULT_USER_DISPLAY_NAME = "Jacob"


def _is_sqlite_engine(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def _table_exists(engine: Engine, table_name: str) -> bool:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = :table_name
                """
            ),
            {"table_name": table_name},
        ).first()
        return row is not None


def _table_columns(engine: Engine, table_name: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in rows}


def migrate_album_artwork_columns(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    columns = _table_columns(engine, "albums")
    if not columns:
        return

    with engine.begin() as connection:
        if "remote_image_url" not in columns:
            connection.execute(text("ALTER TABLE albums ADD COLUMN remote_image_url TEXT"))
            columns.add("remote_image_url")

        if "local_image_path" not in columns:
            connection.execute(text("ALTER TABLE albums ADD COLUMN local_image_path TEXT"))
            columns.add("local_image_path")

        connection.execute(
            text(
                """
                UPDATE albums
                SET remote_image_url = image_url
                WHERE (remote_image_url IS NULL OR remote_image_url = '')
                  AND image_url IS NOT NULL
                  AND image_url != ''
                """
            )
        )


def migrate_default_user(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "users"):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO users (slug, display_name, is_active)
                VALUES (:slug, :display_name, 1)
                """
            ),
            {
                "slug": DEFAULT_USER_SLUG,
                "display_name": DEFAULT_USER_DISPLAY_NAME,
            },
        )


def migrate_user_app_state(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "app_state") or not _table_exists(
        engine,
        "user_app_state",
    ):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO user_app_state (user_id, key, value)
                SELECT users.id, app_state.key, app_state.value
                FROM app_state
                JOIN users ON users.slug = :slug
                WHERE app_state.key = 'last_checked'
                """
            ),
            {"slug": DEFAULT_USER_SLUG},
        )


def migrate_user_albums(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "users") or not _table_exists(engine, "user_albums"):
        return

    if not _table_exists(engine, "albums") or not _table_exists(engine, "album_listens"):
        return

    listen_columns = _table_columns(engine, "album_listens")
    if "user_id" in listen_columns:
        return

    user_album_columns = _table_columns(engine, "user_albums")
    with engine.begin() as connection:
        if "your_tags" in user_album_columns:
            connection.execute(
                text(
                    """
                    INSERT OR IGNORE INTO user_albums (user_id, album_id, your_tags)
                    SELECT users.id, albums.id, '[]'
                    FROM albums
                    JOIN users ON users.slug = :slug
                    """
                ),
                {"slug": DEFAULT_USER_SLUG},
            )
        else:
            connection.execute(
                text(
                    """
                    INSERT OR IGNORE INTO user_albums (user_id, album_id)
                    SELECT users.id, albums.id
                    FROM albums
                    JOIN users ON users.slug = :slug
                    """
                ),
                {"slug": DEFAULT_USER_SLUG},
            )


def cleanup_default_user_cross_user_album_memberships(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    required_tables = {"users", "user_albums", "album_listens", "albums"}
    if any(not _table_exists(engine, table_name) for table_name in required_tables):
        return

    user_album_columns = _table_columns(engine, "user_albums")
    if not {"your_tags", "rating", "notes"}.issubset(user_album_columns):
        return

    other_user_import_clause = ""
    if _table_exists(engine, "imported_listening_events"):
        imported_event_columns = _table_columns(engine, "imported_listening_events")
        if {"user_id", "album_id"}.issubset(imported_event_columns):
            other_user_import_clause = """
                OR EXISTS (
                    SELECT 1
                    FROM imported_listening_events imported
                    WHERE imported.album_id = user_albums.album_id
                      AND imported.user_id != user_albums.user_id
                )
            """

    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                DELETE FROM user_albums
                WHERE user_id = (
                    SELECT id
                    FROM users
                    WHERE slug = :slug
                )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM album_listens own_listens
                    WHERE own_listens.user_id = user_albums.user_id
                      AND own_listens.album_id = user_albums.album_id
                  )
                  AND (
                    your_tags IS NULL
                    OR your_tags = ''
                    OR your_tags = '[]'
                  )
                  AND rating IS NULL
                  AND (
                    notes IS NULL
                    OR trim(notes) = ''
                  )
                  AND EXISTS (
                    SELECT 1
                    FROM albums
                    WHERE albums.id = user_albums.album_id
                      AND COALESCE(albums.entry_source, albums.source, '') != 'manual'
                  )
                  AND (
                    EXISTS (
                        SELECT 1
                        FROM user_albums other_membership
                        WHERE other_membership.album_id = user_albums.album_id
                          AND other_membership.user_id != user_albums.user_id
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM album_listens other_listens
                        WHERE other_listens.album_id = user_albums.album_id
                          AND other_listens.user_id != user_albums.user_id
                    )
                    {other_user_import_clause}
                  )
                """
            ),
            {"slug": DEFAULT_USER_SLUG},
        )


def migrate_album_listens_user_scope(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "album_listens"):
        return

    columns = _table_columns(engine, "album_listens")
    if "user_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE album_listens_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    album_id INTEGER NOT NULL,
                    listened_at VARCHAR NOT NULL,
                    source VARCHAR NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(album_id) REFERENCES albums (id),
                    CONSTRAINT uq_user_album_listen_once
                        UNIQUE (user_id, album_id, listened_at)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO album_listens_new (
                    id,
                    user_id,
                    album_id,
                    listened_at,
                    source
                )
                SELECT
                    album_listens.id,
                    users.id,
                    album_listens.album_id,
                    album_listens.listened_at,
                    COALESCE(album_listens.source, 'unknown')
                FROM album_listens
                JOIN users ON users.slug = :slug
                """
            ),
            {"slug": DEFAULT_USER_SLUG},
        )
        connection.execute(text("DROP TABLE album_listens"))
        connection.execute(text("ALTER TABLE album_listens_new RENAME TO album_listens"))
        connection.execute(
            text("CREATE INDEX ix_album_listens_album_id ON album_listens (album_id)")
        )
        connection.execute(
            text("CREATE INDEX ix_album_listens_user_id ON album_listens (user_id)")
        )
        connection.execute(
            text("CREATE INDEX ix_album_listens_listened_at ON album_listens (listened_at)")
        )
        connection.execute(text("PRAGMA foreign_keys = ON"))


def migrate_albums_in_progress_user_scope(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "albums_in_progress"):
        return

    columns = _table_columns(engine, "albums_in_progress")
    if "user_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE albums_in_progress_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    spotify_album_id VARCHAR NOT NULL,
                    album_name VARCHAR NOT NULL,
                    artist VARCHAR NOT NULL,
                    total_tracks INTEGER NOT NULL,
                    played_tracks JSON NOT NULL,
                    first_played VARCHAR NOT NULL,
                    last_played VARCHAR NOT NULL,
                    completion_logged BOOLEAN,
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    CONSTRAINT uq_user_album_in_progress
                        UNIQUE (user_id, spotify_album_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO albums_in_progress_new (
                    user_id,
                    spotify_album_id,
                    album_name,
                    artist,
                    total_tracks,
                    played_tracks,
                    first_played,
                    last_played,
                    completion_logged
                )
                SELECT
                    users.id,
                    albums_in_progress.spotify_album_id,
                    albums_in_progress.album_name,
                    albums_in_progress.artist,
                    albums_in_progress.total_tracks,
                    albums_in_progress.played_tracks,
                    albums_in_progress.first_played,
                    albums_in_progress.last_played,
                    albums_in_progress.completion_logged
                FROM albums_in_progress
                JOIN users ON users.slug = :slug
                """
            ),
            {"slug": DEFAULT_USER_SLUG},
        )
        connection.execute(text("DROP TABLE albums_in_progress"))
        connection.execute(
            text("ALTER TABLE albums_in_progress_new RENAME TO albums_in_progress")
        )
        connection.execute(
            text(
                "CREATE INDEX ix_albums_in_progress_user_id "
                "ON albums_in_progress (user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX ix_albums_in_progress_spotify_album_id "
                "ON albums_in_progress (spotify_album_id)"
            )
        )
        connection.execute(text("PRAGMA foreign_keys = ON"))


def migrate_user_album_tags(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "user_albums"):
        return

    columns = _table_columns(engine, "user_albums")
    if "your_tags" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE user_albums ADD COLUMN your_tags JSON"))
        connection.execute(
            text(
                """
                UPDATE user_albums
                SET your_tags = '[]'
                WHERE your_tags IS NULL OR your_tags = ''
                """
            )
        )


def migrate_user_album_feedback(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "user_albums"):
        return

    columns = _table_columns(engine, "user_albums")

    with engine.begin() as connection:
        if "rating" not in columns:
            connection.execute(text("ALTER TABLE user_albums ADD COLUMN rating INTEGER"))
            columns.add("rating")

        if "notes" not in columns:
            connection.execute(text("ALTER TABLE user_albums ADD COLUMN notes TEXT"))
            columns.add("notes")


def migrate_album_entry_source(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "albums"):
        return

    columns = _table_columns(engine, "albums")

    with engine.begin() as connection:
        if "entry_source" not in columns:
            connection.execute(text("ALTER TABLE albums ADD COLUMN entry_source VARCHAR"))
            columns.add("entry_source")

        connection.execute(
            text(
                """
                UPDATE albums
                SET entry_source = CASE
                    WHEN source = 'manual' THEN 'manual'
                    WHEN source = 'csv' THEN 'csv_upload'
                    WHEN source = 'lastfm' THEN 'lastfm_import'
                    WHEN source = 'spotify_export' THEN 'spotify_export_upload'
                    WHEN source = 'musicbrainz' THEN 'spotify_sync'
                    WHEN source = 'unknown' THEN 'unknown'
                    WHEN source IS NULL OR source = '' THEN 'unknown'
                    ELSE lower(source)
                END
                WHERE entry_source IS NULL OR entry_source = ''
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_albums_entry_source ON albums (entry_source)"
            )
        )


def migrate_album_canonical_identity(engine: Engine) -> None:
    """Backfill and safely consolidate identities before enforcing indexes."""
    if not _is_sqlite_engine(engine) or not _table_exists(engine, "albums"):
        return

    columns = _table_columns(engine, "albums")
    identity_column_added = "normalized_identity" not in columns
    with engine.begin() as connection:
        if identity_column_added:
            connection.execute(text("ALTER TABLE albums ADD COLUMN normalized_identity VARCHAR"))

    # Some historical test/database snapshots predate the metadata columns
    # required by the ORM mapping. Their existing migrations remain responsible
    # for bringing that schema forward before this identity migration runs.
    required_columns = {"artist", "name", "artist_mbid", "release_group_mbid"}
    if not required_columns.issubset(_table_columns(engine, "albums")):
        return

    from backend.app.album_identity import normalized_artist_title_identity

    # The repository merge preserves per-user fields and moves raw import
    # provenance.  Import lazily to avoid the database module import cycle.
    with engine.connect() as connection:
        raw_rows = connection.execute(
            text("SELECT id, artist, name, release_group_mbid, metadata_json FROM albums")
        ).mappings().all()
    # Old databases can contain malformed JSON metadata. The normal repository
    # already tolerates that on reads; defer reconciliation rather than making
    # startup fail while SQLAlchemy deserializes such a row.
    if any(
        row["metadata_json"] and not _is_valid_json(row["metadata_json"])
        for row in raw_rows
    ):
        with engine.begin() as connection:
            for row in raw_rows:
                connection.execute(
                    text("UPDATE albums SET normalized_identity = :identity WHERE id = :id"),
                    {
                        "id": row["id"],
                        "identity": normalized_artist_title_identity(row["artist"], row["name"]),
                    },
                )
        return

    from sqlalchemy.orm import sessionmaker
    from backend.app.models import Album
    from backend.app.repositories.sqlite_state_repository import SqliteStateRepository

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as session:
        repository = SqliteStateRepository(session)
        remaining = list(session.scalars(select(Album).order_by(Album.id)))
        if identity_column_added:
            by_text_identity: dict[str, list[Album]] = {}
            for album in remaining:
                identity = normalized_artist_title_identity(album.artist, album.name)
                by_text_identity.setdefault(identity, []).append(album)
            for group in by_text_identity.values():
                target = group[0]
                for duplicate in group[1:]:
                    if (
                        target.release_group_mbid
                        and duplicate.release_group_mbid
                        and target.release_group_mbid.casefold()
                        != duplicate.release_group_mbid.casefold()
                    ):
                        continue
                    repository.merge_completed_album_listens(duplicate.id, target.id)

        # A matching release-group MBID is authoritative and safe even where
        # display text changed between sources.
        remaining = list(session.scalars(select(Album).order_by(Album.id)))
        by_release_group: dict[str, list[Album]] = {}
        for album in remaining:
            if album.release_group_mbid:
                by_release_group.setdefault(album.release_group_mbid.casefold(), []).append(album)
        for group in by_release_group.values():
            target = group[0]
            for duplicate in group[1:]:
                repository.merge_completed_album_listens(duplicate.id, target.id)
        for album in session.scalars(select(Album)):
            album.normalized_identity = normalized_artist_title_identity(album.artist, album.name)
        session.commit()

    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_albums_normalized_identity ON albums (normalized_identity)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_albums_release_group_mbid ON albums (release_group_mbid) WHERE release_group_mbid IS NOT NULL AND release_group_mbid != ''"))


def _is_valid_json(value) -> bool:
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True


def migrate_imported_event_candidate_key(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "imported_listening_events"):
        return

    columns = _table_columns(engine, "imported_listening_events")

    with engine.begin() as connection:
        if "candidate_key" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE imported_listening_events ADD COLUMN candidate_key VARCHAR"
                )
            )
            columns.add("candidate_key")

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_imported_listening_events_candidate_key "
                "ON imported_listening_events (candidate_key)"
            )
        )


def migrate_album_metadata_cache(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS album_metadata_cache (
                    id INTEGER NOT NULL PRIMARY KEY,
                    cache_key VARCHAR NOT NULL UNIQUE,
                    artist VARCHAR NOT NULL,
                    album VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    metadata_json JSON NOT NULL,
                    error_message TEXT,
                    updated_at VARCHAR NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_album_metadata_cache_cache_key "
                "ON album_metadata_cache (cache_key)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_album_metadata_cache_status "
                "ON album_metadata_cache (status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_album_metadata_cache_updated_at "
                "ON album_metadata_cache (updated_at)"
            )
        )


def migrate_import_sessions_artifact_path(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "import_sessions"):
        return

    columns = _table_columns(engine, "import_sessions")
    if "artifact_path" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE import_sessions ADD COLUMN artifact_path TEXT"))


def migrate_profile_ownership(engine: Engine) -> None:
    """Fail closed for profiles created before authenticated ownership existed.

    Existing Spotify refresh tokens cannot be safely attributed to a newly
    introduced account, so they are removed once when adding the ownership
    column. The profile data remains public and intact, but must be claimed by
    an explicit future migration rather than becoming writable by URL alone.
    """
    if not _is_sqlite_engine(engine) or not _table_exists(engine, "users"):
        return

    columns = _table_columns(engine, "users")
    if "owner_account_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN owner_account_id INTEGER"))
        if _table_exists(engine, "user_spotify_credentials"):
            connection.execute(text("DELETE FROM user_spotify_credentials"))


def migrate_google_account_identity(engine: Engine) -> None:
    if not _is_sqlite_engine(engine) or not _table_exists(engine, "accounts"):
        return
    columns = _table_columns(engine, "accounts")
    with engine.begin() as connection:
        if "google_subject" not in columns:
            connection.execute(text("ALTER TABLE accounts ADD COLUMN google_subject VARCHAR"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_google_subject ON accounts (google_subject)"))


def migrate_import_session_source_metadata(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    if not _table_exists(engine, "import_sessions"):
        return

    columns = _table_columns(engine, "import_sessions")
    source_columns = {
        "original_filename": "VARCHAR",
        "file_size_bytes": "INTEGER",
        "file_sha256": "VARCHAR",
        "zip_member_count": "INTEGER",
        "duplicate_of_import_session_id": "INTEGER",
    }
    with engine.begin() as connection:
        for column, column_type in source_columns.items():
            if column not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE import_sessions "
                        f"ADD COLUMN {column} {column_type}"
                    )
                )
                columns.add(column)
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_import_sessions_file_sha256 "
                "ON import_sessions (file_sha256)"
            )
        )


def migrate_spotify_streaming_events(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS spotify_streaming_events (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    import_session_id INTEGER,
                    event_fingerprint VARCHAR NOT NULL,
                    source_file VARCHAR,
                    source_index INTEGER,
                    played_at VARCHAR NOT NULL,
                    ms_played INTEGER NOT NULL,
                    spotify_track_uri VARCHAR,
                    spotify_track_id VARCHAR,
                    spotify_album_id VARCHAR,
                    spotify_album_name VARCHAR,
                    spotify_album_artist_name VARCHAR,
                    spotify_album_total_tracks INTEGER,
                    spotify_album_type VARCHAR,
                    spotify_disc_number INTEGER,
                    spotify_track_number INTEGER,
                    spotify_catalog_status VARCHAR,
                    track_name VARCHAR,
                    artist_name VARCHAR,
                    album_name VARCHAR,
                    platform VARCHAR,
                    country VARCHAR,
                    reason_start VARCHAR,
                    reason_end VARCHAR,
                    skipped BOOLEAN,
                    offline BOOLEAN,
                    raw_payload JSON NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(import_session_id) REFERENCES import_sessions (id),
                    CONSTRAINT uq_spotify_streaming_event_fingerprint
                        UNIQUE (user_id, event_fingerprint)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_user_id "
                "ON spotify_streaming_events (user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_import_session_id "
                "ON spotify_streaming_events (import_session_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_event_fingerprint "
                "ON spotify_streaming_events (event_fingerprint)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_played_at "
                "ON spotify_streaming_events (played_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_spotify_track_uri "
                "ON spotify_streaming_events (spotify_track_uri)"
            )
        )
        columns = _table_columns(engine, "spotify_streaming_events")
        spotify_event_columns = {
            "source_file": "VARCHAR",
            "source_index": "INTEGER",
            "spotify_track_id": "VARCHAR",
            "spotify_album_id": "VARCHAR",
            "spotify_album_name": "VARCHAR",
            "spotify_album_artist_name": "VARCHAR",
            "spotify_album_total_tracks": "INTEGER",
            "spotify_album_type": "VARCHAR",
            "spotify_disc_number": "INTEGER",
            "spotify_track_number": "INTEGER",
            "spotify_catalog_status": "VARCHAR",
        }
        for column, column_type in spotify_event_columns.items():
            if column not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE spotify_streaming_events "
                        f"ADD COLUMN {column} {column_type}"
                    )
                )
                columns.add(column)
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_spotify_track_id "
                "ON spotify_streaming_events (spotify_track_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_spotify_album_id "
                "ON spotify_streaming_events (spotify_album_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_spotify_catalog_status "
                "ON spotify_streaming_events (spotify_catalog_status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_spotify_streaming_events_spotify_album_type "
                "ON spotify_streaming_events (spotify_album_type)"
            )
        )


def migrate_import_session_logs(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS import_session_logs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    import_session_id INTEGER NOT NULL,
                    created_at VARCHAR NOT NULL,
                    level VARCHAR NOT NULL,
                    stage VARCHAR,
                    message TEXT NOT NULL,
                    artist VARCHAR,
                    album VARCHAR,
                    current INTEGER,
                    total INTEGER,
                    elapsed_seconds FLOAT,
                    metadata_json JSON NOT NULL,
                    FOREIGN KEY(import_session_id) REFERENCES import_sessions (id)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_import_session_logs_import_session_id "
                "ON import_session_logs (import_session_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_import_session_logs_created_at "
                "ON import_session_logs (created_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_import_session_logs_stage "
                "ON import_session_logs (stage)"
            )
        )


def migrate_album_credit_facts(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS album_credit_facts (
                    id INTEGER NOT NULL PRIMARY KEY,
                    album_id INTEGER NOT NULL,
                    person_key VARCHAR NOT NULL,
                    person_name VARCHAR NOT NULL,
                    person_mbid VARCHAR,
                    identity_resolution VARCHAR NOT NULL,
                    ingestion_version VARCHAR NOT NULL,
                    raw_role VARCHAR NOT NULL,
                    role_bucket VARCHAR NOT NULL,
                    source_scope VARCHAR NOT NULL,
                    recording_mbid VARCHAR,
                    track_count INTEGER NOT NULL,
                    album_track_count INTEGER NOT NULL,
                    track_share FLOAT NOT NULL,
                    quality_flags_json JSON NOT NULL,
                    created_at VARCHAR NOT NULL,
                    updated_at VARCHAR NOT NULL,
                    FOREIGN KEY(album_id) REFERENCES albums (id),
                    CONSTRAINT uq_album_credit_fact_identity_role_scope
                        UNIQUE (
                            album_id,
                            person_key,
                            raw_role,
                            source_scope,
                            ingestion_version
                        )
                )
                """
            )
        )
        for name, column in {
            "ix_album_credit_facts_album_id": "album_id",
            "ix_album_credit_facts_person_key": "person_key",
            "ix_album_credit_facts_person_name": "person_name",
            "ix_album_credit_facts_person_mbid": "person_mbid",
            "ix_album_credit_facts_identity_resolution": "identity_resolution",
            "ix_album_credit_facts_ingestion_version": "ingestion_version",
            "ix_album_credit_facts_raw_role": "raw_role",
            "ix_album_credit_facts_role_bucket": "role_bucket",
            "ix_album_credit_facts_source_scope": "source_scope",
            "ix_album_credit_facts_recording_mbid": "recording_mbid",
            "ix_album_credit_facts_created_at": "created_at",
            "ix_album_credit_facts_updated_at": "updated_at",
        }.items():
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {name} "
                    f"ON album_credit_facts ({column})"
                )
        )


def migrate_single_profile_ownership(engine: Engine) -> None:
    if not _is_sqlite_engine(engine) or not _table_exists(engine, "users"):
        return

    with engine.begin() as connection:
        duplicate_account_ids = connection.execute(
            text(
                """
                SELECT owner_account_id
                FROM users
                WHERE owner_account_id IS NOT NULL
                GROUP BY owner_account_id
                HAVING COUNT(*) > 1
                """
            )
        ).scalars().all()
        if duplicate_account_ids:
            raise RuntimeError(
                "Cannot enforce one-profile-per-account while duplicate profile "
                "ownership assignments exist for account IDs: "
                + ", ".join(str(account_id) for account_id in duplicate_account_ids)
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_owner_account_id "
                "ON users (owner_account_id) WHERE owner_account_id IS NOT NULL"
            )
        )


def run_sqlite_migrations(engine: Engine) -> None:
    migrate_default_user(engine)
    migrate_album_artwork_columns(engine)
    migrate_user_app_state(engine)
    migrate_user_albums(engine)
    migrate_album_listens_user_scope(engine)
    migrate_albums_in_progress_user_scope(engine)
    migrate_user_album_tags(engine)
    migrate_user_album_feedback(engine)
    migrate_album_entry_source(engine)
    migrate_album_canonical_identity(engine)
    cleanup_default_user_cross_user_album_memberships(engine)
    migrate_imported_event_candidate_key(engine)
    migrate_album_metadata_cache(engine)
    migrate_import_sessions_artifact_path(engine)
    migrate_profile_ownership(engine)
    migrate_google_account_identity(engine)
    migrate_import_session_source_metadata(engine)
    migrate_spotify_streaming_events(engine)
    migrate_import_session_logs(engine)
    migrate_album_credit_facts(engine)
    migrate_single_profile_ownership(engine)
