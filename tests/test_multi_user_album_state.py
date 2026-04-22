import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository


def sample_album_state():
    return {
        "last_checked": "2026-04-18T16:14:25.872Z",
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Shared Album": {
                "artist": "Artist",
                "name": "Shared Album",
                "source": "musicbrainz",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Shared Album"],
    }


class MultiUserAlbumStateTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            repository = SqliteStateRepository(session)
            repository.save_album_state(sample_album_state())

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

    def test_user_scoped_state_keeps_listens_independent_on_shared_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            create_user_response = client.post(
                "/api/users",
                json={"slug": "friend", "display_name": "Friend"},
            )
            self.assertEqual(create_user_response.status_code, 201)

            friend_create_response = client.post(
                "/api/users/friend/albums",
                json={
                    "artist": "Artist",
                    "name": "Shared Album",
                    "listen_date": "2026-04-18T15:45:00.000Z",
                },
            )
            self.assertEqual(friend_create_response.status_code, 201)

            default_state = client.get("/api/album-state").json()
            friend_state = client.get("/api/users/friend/album-state").json()

        self.assertEqual(
            default_state["completed_albums"]["Artist - Shared Album"][
                "listen_history"
            ],
            ["2026-04-18T15:45:00.000Z"],
        )
        self.assertEqual(
            friend_state["completed_albums"]["Artist - Shared Album"][
                "listen_history"
            ],
            ["2026-04-18T15:45:00.000Z"],
        )
        self.assertEqual(friend_state["last_checked"], None)

    def test_user_scoped_listen_mutation_does_not_touch_default_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            client.post("/api/users", json={"slug": "friend", "display_name": "Friend"})
            album_id = client.get("/api/album-state").json()["completed_albums"][
                "Artist - Shared Album"
            ]["id"]

            response = client.post(
                f"/api/users/friend/albums/{album_id}/listens",
                json={"listened_at": "2026-04-19T12:00:00.000Z"},
            )
            default_state = client.get("/api/album-state").json()
            friend_state = client.get("/api/users/friend/album-state").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            default_state["completed_albums"]["Artist - Shared Album"][
                "listen_history"
            ],
            ["2026-04-18T15:45:00.000Z"],
        )
        self.assertEqual(
            friend_state["completed_albums"]["Artist - Shared Album"][
                "listen_history"
            ],
            ["2026-04-19T12:00:00.000Z"],
        )

    def test_user_scoped_tags_do_not_touch_default_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            client.post("/api/users", json={"slug": "friend", "display_name": "Friend"})
            album_id = client.get("/api/album-state").json()["completed_albums"][
                "Artist - Shared Album"
            ]["id"]
            client.post(
                "/api/users/friend/albums",
                json={
                    "artist": "Artist",
                    "name": "Shared Album",
                    "listen_date": "2026-04-18T15:45:00.000Z",
                },
            )

            response = client.put(
                f"/api/users/friend/albums/{album_id}/your-tags",
                json={"your_tags": ["great-imaging", "cohesive"]},
            )
            default_state = client.get("/api/album-state").json()
            friend_state = client.get("/api/users/friend/album-state").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            default_state["completed_albums"]["Artist - Shared Album"]["your_tags"],
            [],
        )
        self.assertEqual(
            friend_state["completed_albums"]["Artist - Shared Album"]["your_tags"],
            ["great-imaging", "cohesive"],
        )


if __name__ == "__main__":
    unittest.main()
