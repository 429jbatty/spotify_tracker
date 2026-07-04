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

    def test_create_schema_backfills_legacy_albums_to_default_user(self):
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
                        INSERT INTO albums (
                            id, album_key, artist, name, image_url, source, metadata_json
                        )
                        VALUES
                            (1, 'Artist - Listened Album', 'Artist', 'Listened Album', NULL, 'unknown', '{}'),
                            (2, 'Artist - Empty Album', 'Artist', 'Empty Album', NULL, 'manual', '{}')
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

            migrated_engine = create_schema(database_url)
            with migrated_engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT albums.album_key
                        FROM user_albums
                        JOIN users ON users.id = user_albums.user_id
                        JOIN albums ON albums.id = user_albums.album_id
                        WHERE users.slug = 'jacob'
                        ORDER BY albums.id
                        """
                    )
                ).all()

        self.assertEqual(
            [row.album_key for row in rows],
            ["Artist - Listened Album", "Artist - Empty Album"],
        )

    def test_create_schema_does_not_backfill_modern_albums_to_default_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            engine = create_schema(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (slug, display_name, is_active)
                        VALUES ('emily', 'Emily', 1)
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
                            source,
                            entry_source,
                            metadata_json
                        )
                        VALUES (
                            1,
                            'Other Artist - Other Album',
                            'Other Artist',
                            'Other Album',
                            'musicbrainz',
                            'spotify_import',
                            '{}'
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO user_albums (user_id, album_id, your_tags)
                        SELECT users.id, 1, '[]'
                        FROM users
                        WHERE users.slug = 'emily'
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            with migrated_engine.connect() as connection:
                jacob_membership = connection.execute(
                    text(
                        """
                        SELECT user_albums.id
                        FROM user_albums
                        JOIN users ON users.id = user_albums.user_id
                        WHERE users.slug = 'jacob'
                          AND user_albums.album_id = 1
                        """
                    )
                ).first()

        self.assertIsNone(jacob_membership)

    def test_create_schema_cleans_cross_user_default_membership_pollution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            engine = create_schema(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (slug, display_name, is_active)
                        VALUES ('emily', 'Emily', 1)
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
                            source,
                            entry_source,
                            metadata_json
                        )
                        VALUES
                            (1, 'Other Artist - Other Album', 'Other Artist', 'Other Album', 'musicbrainz', 'spotify_import', '{}'),
                            (2, 'Jacob Artist - Manual Empty', 'Jacob Artist', 'Manual Empty', 'manual', 'manual', '{}'),
                            (3, 'Tagged Artist - Tagged Album', 'Tagged Artist', 'Tagged Album', 'musicbrainz', 'spotify_import', '{}'),
                            (4, 'Shared Manual Artist - Shared Manual', 'Shared Manual Artist', 'Shared Manual', 'manual', 'manual', '{}')
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO user_albums (user_id, album_id, your_tags, rating, notes)
                        SELECT users.id, 1, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'jacob'
                        UNION ALL
                        SELECT users.id, 1, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'emily'
                        UNION ALL
                        SELECT users.id, 2, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'jacob'
                        UNION ALL
                        SELECT users.id, 3, '["keep"]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'jacob'
                        UNION ALL
                        SELECT users.id, 3, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'emily'
                        UNION ALL
                        SELECT users.id, 4, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'jacob'
                        UNION ALL
                        SELECT users.id, 4, '[]', NULL, NULL
                        FROM users
                        WHERE users.slug = 'emily'
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO album_listens (user_id, album_id, listened_at, source)
                        SELECT users.id, 1, '2026-06-01T10:00:00.000Z', 'spotify_import'
                        FROM users
                        WHERE users.slug = 'emily'
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            with migrated_engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT albums.album_key
                        FROM user_albums
                        JOIN users ON users.id = user_albums.user_id
                        JOIN albums ON albums.id = user_albums.album_id
                        WHERE users.slug = 'jacob'
                        ORDER BY albums.id
                        """
                    )
                ).all()

        self.assertEqual(
            [row.album_key for row in rows],
            [
                "Jacob Artist - Manual Empty",
                "Tagged Artist - Tagged Album",
                "Shared Manual Artist - Shared Manual",
            ],
        )

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

    def test_create_schema_adds_source_metadata_to_existing_import_sessions_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE import_sessions (
                            id INTEGER NOT NULL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            source VARCHAR NOT NULL,
                            source_user_id VARCHAR,
                            status VARCHAR NOT NULL,
                            session_name VARCHAR,
                            started_at VARCHAR NOT NULL,
                            completed_at VARCHAR,
                            summary_json JSON NOT NULL
                        )
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = [
                    row[1]
                    for row in connection.execute(text("PRAGMA table_info(import_sessions)"))
                ]

        self.assertEqual(columns.count("artifact_path"), 1)
        self.assertEqual(columns.count("original_filename"), 1)
        self.assertEqual(columns.count("file_size_bytes"), 1)
        self.assertEqual(columns.count("file_sha256"), 1)
        self.assertEqual(columns.count("zip_member_count"), 1)
        self.assertEqual(columns.count("duplicate_of_import_session_id"), 1)

    def test_create_schema_creates_spotify_streaming_events_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(spotify_streaming_events)")
                    )
                }
                indexes = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA index_list(spotify_streaming_events)")
                    )
                }

        self.assertEqual(
            columns,
            {
                "id",
                "user_id",
                "import_session_id",
                "event_fingerprint",
                "source_file",
                "source_index",
                "played_at",
                "ms_played",
                "spotify_track_uri",
                "spotify_track_id",
                "spotify_album_id",
                "spotify_album_name",
                "spotify_album_artist_name",
                "spotify_album_total_tracks",
                "spotify_album_type",
                "spotify_disc_number",
                "spotify_track_number",
                "spotify_catalog_status",
                "track_name",
                "artist_name",
                "album_name",
                "platform",
                "country",
                "reason_start",
                "reason_end",
                "skipped",
                "offline",
                "raw_payload",
            },
        )
        self.assertIn("ix_spotify_streaming_events_user_id", indexes)
        self.assertIn("ix_spotify_streaming_events_import_session_id", indexes)
        self.assertIn("ix_spotify_streaming_events_played_at", indexes)
        self.assertIn("ix_spotify_streaming_events_spotify_album_id", indexes)

    def test_create_schema_adds_spotify_catalog_columns_to_existing_events_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_engine(database_url)

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE spotify_streaming_events (
                            id INTEGER NOT NULL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            import_session_id INTEGER,
                            event_fingerprint VARCHAR NOT NULL,
                            played_at VARCHAR NOT NULL,
                            ms_played INTEGER NOT NULL,
                            spotify_track_uri VARCHAR,
                            track_name VARCHAR,
                            artist_name VARCHAR,
                            album_name VARCHAR,
                            platform VARCHAR,
                            country VARCHAR,
                            reason_start VARCHAR,
                            reason_end VARCHAR,
                            skipped BOOLEAN,
                            offline BOOLEAN,
                            raw_payload JSON NOT NULL
                        )
                        """
                    )
                )

            migrated_engine = create_schema(database_url)
            create_schema(database_url)
            with migrated_engine.connect() as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(spotify_streaming_events)")
                    )
                }

        self.assertIn("spotify_track_id", columns)
        self.assertIn("spotify_album_id", columns)
        self.assertIn("spotify_album_total_tracks", columns)
        self.assertIn("spotify_album_type", columns)
        self.assertIn("spotify_catalog_status", columns)
        self.assertIn("source_file", columns)
        self.assertIn("source_index", columns)


if __name__ == "__main__":
    unittest.main()
