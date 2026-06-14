import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import UserRepository


class PublicActivityApiTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with session_factory() as session:
            UserRepository(session).create_user(
                slug="friend",
                display_name="Friend",
            )
            SqliteStateRepository(session).save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Artist One - Older Album": {
                            "artist": "Artist One",
                            "name": "Older Album",
                            "image_url": "https://example.com/older.jpg",
                            "source": "manual",
                            "listen_history": ["2026-04-18T15:45:00.000Z"],
                            "rating": 9,
                            "notes": "private note",
                            "your_tags": ["private-tag"],
                        },
                    },
                    "most_recently_listened": ["Artist One - Older Album"],
                }
            )
            SqliteStateRepository(session, user_slug="friend").save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Artist Two - Newer Album": {
                            "artist": "Artist Two",
                            "name": "Newer Album",
                            "local_image_path": "artwork/newer.jpg",
                            "source": "manual",
                            "listen_history": ["2026-04-19T15:45:00.000Z"],
                        },
                    },
                    "most_recently_listened": ["Artist Two - Newer Album"],
                }
            )

        patcher = patch.dict(
            "os.environ",
            {
                "DATABASE_URL": database_url,
                "MEDIA_DIR": temp_dir,
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def test_recent_listens_returns_latest_public_album_fields_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)

            response = client.get("/api/public/recent-listens?limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [
                (
                    album["listener_display_name"],
                    album["listened_at"],
                    album["artist"],
                    album["name"],
                )
                for album in payload
            ],
            [
                (
                    "Friend",
                    "2026-04-19T15:45:00.000Z",
                    "Artist Two",
                    "Newer Album",
                ),
                (
                    "Jacob",
                    "2026-04-18T15:45:00.000Z",
                    "Artist One",
                    "Older Album",
                ),
            ],
        )
        self.assertEqual(payload[0]["image_url"], "/media/artwork/newer.jpg")
        self.assertEqual(
            set(payload[0].keys()),
            {
                "listen_id",
                "listener_display_name",
                "listened_at",
                "album_id",
                "album_key",
                "artist",
                "name",
                "image_url",
            },
        )
        self.assertNotIn("rating", payload[1])
        self.assertNotIn("notes", payload[1])
        self.assertNotIn("your_tags", payload[1])


if __name__ == "__main__":
    unittest.main()
