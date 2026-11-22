import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

from backend.app.database import create_schema


class DatabaseSchemaTests(unittest.TestCase):
    def test_create_schema_creates_album_metadata_cache_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            schema_engine = create_schema(database_url)
            create_schema(database_url)
            with schema_engine.connect() as connection:
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

    def test_create_schema_creates_spotify_streaming_events_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            schema_engine = create_schema(database_url)
            create_schema(database_url)
            with schema_engine.connect() as connection:
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

    def test_create_schema_creates_album_credit_facts_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            schema_engine = create_schema(database_url)
            create_schema(database_url)
            with schema_engine.connect() as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(album_credit_facts)")
                    )
                }
                indexes = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA index_list(album_credit_facts)")
                    )
                }

        self.assertIn("album_id", columns)
        self.assertIn("person_key", columns)
        self.assertIn("person_mbid", columns)
        self.assertIn("identity_resolution", columns)
        self.assertIn("ingestion_version", columns)
        self.assertIn("quality_flags_json", columns)
        self.assertIn("ix_album_credit_facts_person_key", indexes)
        self.assertIn("ix_album_credit_facts_role_bucket", indexes)

    def test_restart_preserves_populated_profiles_and_ignores_retired_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "current.sqlite"
            url = f"sqlite:///{path}"
            create_schema(url).dispose()
            with sqlite3.connect(path) as db:
                self.assertEqual(
                    db.execute("SELECT slug, display_name, is_active, spotify_sync_enabled FROM users").fetchall(),
                    [("jacob", "Jacob", 1, 0)],
                )
                db.executescript("""
                    INSERT INTO accounts (id, email, password_hash, created_at)
                    VALUES (1, 'owner@example.test', 'disabled', '2026-01-01');
                    UPDATE users SET display_name='Existing', owner_account_id=1,
                        spotify_sync_enabled=1 WHERE slug='jacob';
                    INSERT INTO users (id, slug, display_name, is_active) VALUES (2, 'other', 'Other', 1);
                    INSERT INTO user_spotify_credentials (user_id, refresh_token) VALUES (1, 'test-token');
                    INSERT INTO albums (id, album_key, artist, name, source, entry_source, metadata_json)
                    VALUES (1, 'A - B', 'A', 'B', 'musicbrainz', 'spotify_sync', '{}');
                    INSERT INTO user_albums (user_id, album_id, your_tags) VALUES (2, 1, '["lush"]');
                    INSERT INTO album_listens (user_id, album_id, listened_at, source)
                    VALUES (2, 1, '2026-02-01', 'manual');
                    CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);
                    INSERT INTO app_state VALUES ('last_checked', 'retired-cursor');
                """)
                # Databases upgraded in place enforce ownership via the partial
                # index. Fresh ORM-created tables also have a redundant index.
                db.execute("DROP INDEX ix_users_owner_account_id")
                before = list(db.iterdump())

            create_schema(url).dispose()
            with sqlite3.connect(path) as db:
                self.assertEqual(list(db.iterdump()), before)
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE users SET owner_account_id=1 WHERE slug='other'")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_uniqueness_allows_missing_release_groups_and_unowned_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh.sqlite"
            create_schema(f"sqlite:///{path}").dispose()
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                insert_album = """
                    INSERT INTO albums (album_key, artist, name, release_group_mbid, source, entry_source, metadata_json)
                    VALUES (?, 'Artist', 'Title', ?, 'manual', 'manual', '{}')
                """
                for i, mbid in enumerate([None, None, "", "", "group"]):
                    db.execute(insert_album, (str(i), mbid))
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(insert_album, ("duplicate", "group"))

                db.execute("""INSERT INTO accounts (id, email, password_hash, created_at)
                              VALUES (1, 'owner@example.test', 'disabled', '2026-01-01')""")
                add_user = "INSERT INTO users (slug, display_name, is_active, owner_account_id) VALUES (?, 'Profile', 1, ?)"
                for slug, owner in [("unowned", None), ("owned", 1)]:
                    db.execute(add_user, (slug, owner))
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(add_user, ("duplicate", 1))
