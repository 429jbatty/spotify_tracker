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


if __name__ == "__main__":
    unittest.main()
