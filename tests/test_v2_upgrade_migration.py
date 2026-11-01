import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

from backend.app.album_identity import normalized_artist_title_identity
from backend.app.database import create_schema
from tests.v2_upgrade_fixture import create_v2_database


class V2UpgradeMigrationTests(unittest.TestCase):
    def _assert_upgrade(self, *, partially_migrated):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.sqlite"
            create_v2_database(path, partially_migrated=partially_migrated)
            database_url = f"sqlite:///{path}"
            engine = create_schema(database_url)
            try:
                with engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text(
                            "SELECT id, normalized_identity FROM albums ORDER BY id"
                        )).all(),
                        [(1, normalized_artist_title_identity("Artist", "Album"))],
                    )
                    self.assertEqual(
                        connection.execute(text(
                            "SELECT user_id, album_id, listened_at FROM album_listens "
                            "ORDER BY user_id, listened_at"
                        )).all(),
                        [(1, 1, '2026-01-01T10:00:00Z'),
                         (1, 1, '2026-01-02T10:00:00Z'),
                         (2, 1, '2026-01-03T10:00:00Z')],
                    )
                    rows = connection.execute(text(
                        "SELECT user_id, your_tags, rating, notes FROM user_albums "
                        "ORDER BY user_id"
                    )).all()
                    self.assertEqual(
                        [(row.user_id, json.loads(row.your_tags), row.rating, row.notes)
                         for row in rows],
                        [(1, ['atmospheric', 'lush'], 4, 'Original note'),
                         (2, ['raw'], 2, 'Other note')],
                    )
                    self.assertEqual(connection.execute(text(
                        "SELECT album_id FROM imported_listening_events"
                    )).scalar_one(), 1)
                    self.assertEqual(connection.execute(text(
                        "SELECT count(*) FROM user_spotify_credentials"
                    )).scalar_one(), 0)
                    self.assertEqual(connection.execute(text(
                        "SELECT owner_account_id, spotify_sync_enabled FROM users "
                        "ORDER BY id"
                    )).all(), [(None, 0), (None, 0)])
                    self.assertEqual(connection.execute(text(
                        "PRAGMA foreign_key_check"
                    )).all(), [])
                    self.assertEqual(connection.execute(text(
                        "PRAGMA integrity_check"
                    )).scalar_one(), 'ok')

                # A later startup must preserve credentials reconnected after migration.
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO user_spotify_credentials (user_id, refresh_token) "
                        "VALUES (1, 'reconnected-token')"
                    ))
                repeated_engine = create_schema(database_url)
                try:
                    with repeated_engine.connect() as connection:
                        self.assertEqual(connection.execute(text(
                            "SELECT refresh_token FROM user_spotify_credentials"
                        )).scalar_one(), 'reconnected-token')
                        self.assertEqual(connection.execute(text(
                            "SELECT count(*) FROM album_listens"
                        )).scalar_one(), 3)
                finally:
                    repeated_engine.dispose()
            finally:
                engine.dispose()

    def test_upgrade_from_actual_v2_schema(self):
        self._assert_upgrade(partially_migrated=False)

    def test_upgrade_after_failed_v3_column_additions(self):
        self._assert_upgrade(partially_migrated=True)
