from sqlalchemy import Engine, text

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

    if not _table_exists(engine, "albums"):
        return

    with engine.begin() as connection:
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
    migrate_imported_event_candidate_key(engine)
    migrate_album_metadata_cache(engine)
