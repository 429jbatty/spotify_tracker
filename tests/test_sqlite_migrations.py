import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.app.database import create_schema


class SqliteMigrationTests(unittest.TestCase):
    def test_create_schema_adds_artwork_columns_to_existing_albums_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE albums (
                            id INTEGER NOT NULL PRIMARY KEY,
                            album_key VARCHAR NOT NULL,
                            artist VARCHAR NOT NULL,
                            name VARCHAR NOT NULL,
                            image_url TEXT,
                            source VARCHAR NOT NULL,
                            metadata_json JSON NOT NULL
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO albums (
                            id,
                            album_key,
                            artist,
                            name,
                            image_url,
                            source,
                            metadata_json
                        )
                        VALUES (
                            1,
                            'Artist - Album',
                            'Artist',
                            'Album',
                            'https://example.test/cover.jpg',
                            'musicbrainz',
                            '{}'
                        )
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = {
                    row[1] for row in connection.execute(text("PRAGMA table_info(albums)"))
                }
                row = connection.execute(
                    text(
                        """
                        SELECT image_url, remote_image_url, local_image_path
                        FROM albums
                        WHERE album_key = 'Artist - Album'
                        """
                    )
                ).one()

        self.assertIn("remote_image_url", columns)
        self.assertIn("local_image_path", columns)
        self.assertEqual(row.image_url, "https://example.test/cover.jpg")
        self.assertEqual(row.remote_image_url, "https://example.test/cover.jpg")
        self.assertIsNone(row.local_image_path)

    def test_create_schema_artwork_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            create_schema(database_url)
            create_schema(database_url)

            engine = create_engine(database_url)
            with engine.connect() as connection:
                columns = [
                    row[1] for row in connection.execute(text("PRAGMA table_info(albums)"))
                ]

        self.assertEqual(columns.count("remote_image_url"), 1)
        self.assertEqual(columns.count("local_image_path"), 1)

    def test_create_schema_migrates_existing_state_to_default_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE albums (
                            id INTEGER NOT NULL PRIMARY KEY,
                            album_key VARCHAR NOT NULL,
                            artist VARCHAR NOT NULL,
                            name VARCHAR NOT NULL,
                            image_url TEXT,
                            source VARCHAR NOT NULL,
                            metadata_json JSON NOT NULL
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        CREATE TABLE album_listens (
                            id INTEGER NOT NULL PRIMARY KEY,
                            album_id INTEGER NOT NULL,
                            listened_at VARCHAR NOT NULL,
                            source VARCHAR NOT NULL,
                            CONSTRAINT uq_album_listen_once
                                UNIQUE (album_id, listened_at)
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        CREATE TABLE albums_in_progress (
                            spotify_album_id VARCHAR NOT NULL PRIMARY KEY,
                            album_name VARCHAR NOT NULL,
                            artist VARCHAR NOT NULL,
                            total_tracks INTEGER NOT NULL,
                            played_tracks JSON NOT NULL,
                            first_played VARCHAR NOT NULL,
                            last_played VARCHAR NOT NULL,
                            completion_logged BOOLEAN
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        CREATE TABLE app_state (
                            key VARCHAR NOT NULL PRIMARY KEY,
                            value TEXT
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO albums (
                            id, album_key, artist, name, image_url, source, metadata_json
                        )
                        VALUES (
                            1, 'Artist - Album', 'Artist', 'Album', NULL, 'unknown', '{}'
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO album_listens (id, album_id, listened_at, source)
                        VALUES (1, 1, '2026-04-18T10:00:00.000Z', 'spotify')
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO albums_in_progress (
                            spotify_album_id,
                            album_name,
                            artist,
                            total_tracks,
                            played_tracks,
                            first_played,
                            last_played,
                            completion_logged
                        )
                        VALUES (
                            'spotify-album',
                            'Album',
                            'Artist',
                            2,
                            '["track-1"]',
                            '2026-04-18T10:00:00.000Z',
                            '2026-04-18T10:02:00.000Z',
                            0
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO app_state (key, value)
                        VALUES ('last_checked', '2026-04-18T10:02:00.000Z')
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            with migrated_engine.connect() as connection:
                listen_columns = {
                    row[1]
                    for row in connection.execute(text("PRAGMA table_info(album_listens)"))
                }
                in_progress_columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(albums_in_progress)")
                    )
                }
                row = connection.execute(
                    text(
                        """
                        SELECT u.slug, l.listened_at, s.value
                        FROM album_listens l
                        JOIN users u ON u.id = l.user_id
                        JOIN user_app_state s ON s.user_id = u.id
                        WHERE s.key = 'last_checked'
                        """
                    )
                ).one()

        self.assertIn("user_id", listen_columns)
        self.assertIn("user_id", in_progress_columns)
        self.assertEqual(row.slug, "jacob")
        self.assertEqual(row.listened_at, "2026-04-18T10:00:00.000Z")
        self.assertEqual(row.value, "2026-04-18T10:02:00.000Z")

    def test_create_schema_backfills_album_entry_source_from_legacy_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE albums (
                            id INTEGER NOT NULL PRIMARY KEY,
                            album_key VARCHAR NOT NULL,
                            artist VARCHAR NOT NULL,
                            name VARCHAR NOT NULL,
                            image_url TEXT,
                            source VARCHAR NOT NULL,
                            metadata_json JSON NOT NULL
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO albums (
                            id, album_key, artist, name, image_url, source, metadata_json
                        )
                        VALUES
                            (1, 'Manual Artist - Album', 'Manual Artist', 'Album', NULL, 'manual', '{}'),
                            (2, 'CSV Artist - Album', 'CSV Artist', 'Album', NULL, 'csv', '{}'),
                            (3, 'Lastfm Artist - Album', 'Lastfm Artist', 'Album', NULL, 'lastfm', '{}'),
                            (4, 'Spotify Artist - Album', 'Spotify Artist', 'Album', NULL, 'musicbrainz', '{}')
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = {
                    row[1] for row in connection.execute(text("PRAGMA table_info(albums)"))
                }
                rows = connection.execute(
                    text("SELECT source, entry_source FROM albums ORDER BY id")
                ).all()

        self.assertIn("entry_source", columns)
        self.assertEqual(
            [(row.source, row.entry_source) for row in rows],
            [
                ("manual", "manual"),
                ("csv", "csv_upload"),
                ("lastfm", "lastfm_import"),
                ("musicbrainz", "spotify_sync"),
            ],
        )

    def test_create_schema_adds_candidate_key_to_existing_imported_events_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE imported_listening_events (
                            id INTEGER NOT NULL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            import_session_id INTEGER,
                            album_id INTEGER,
                            source VARCHAR NOT NULL,
                            source_user_id VARCHAR,
                            source_event_id VARCHAR,
                            event_fingerprint VARCHAR NOT NULL,
                            listened_at VARCHAR NOT NULL,
                            artist VARCHAR NOT NULL,
                            album VARCHAR,
                            track VARCHAR,
                            source_label VARCHAR,
                            rating INTEGER,
                            notes TEXT,
                            match_status VARCHAR NOT NULL,
                            match_confidence INTEGER,
                            error_message TEXT,
                            raw_payload JSON NOT NULL
                        )
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = [
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(imported_listening_events)")
                    )
                ]

        self.assertEqual(columns.count("candidate_key"), 1)

    def test_create_schema_creates_album_metadata_cache_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(album_metadata_cache)")
                    )
                }
                indexes = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA index_list(album_metadata_cache)")
                    )
                }

        self.assertEqual(
            columns,
            {
                "id",
                "cache_key",
                "artist",
                "album",
                "status",
                "metadata_json",
                "error_message",
                "updated_at",
            },
        )
        self.assertIn("ix_album_metadata_cache_cache_key", indexes)
        self.assertIn("ix_album_metadata_cache_status", indexes)
        self.assertIn("ix_album_metadata_cache_updated_at", indexes)


if __name__ == "__main__":
    unittest.main()
