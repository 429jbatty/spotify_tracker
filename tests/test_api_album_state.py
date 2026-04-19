import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.database import create_schema
from backend.app.models import Album
from backend.app.main import create_app
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def sample_album_state():
    return {
        "last_checked": "2026-04-18T16:14:25.872Z",
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Finished Album": {
                "artist": "Artist",
                "name": "Finished Album",
                "release_year": 2026,
                "release_month": 4,
                "release_day": 18,
                "tracklist": [
                    {
                        "position": "1",
                        "title": "Opening Track",
                        "credits": [["Producer", "producer", ""]],
                        "recording_mbid": "recording-mbid",
                    }
                ],
                "genres": ["rock"],
                "tags": ["indie"],
                "image_url": "https://example.test/cover.jpg",
                "source": "musicbrainz",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Finished Album"],
    }


class ApiAlbumStateTests(unittest.TestCase):
    def test_album_state_endpoint_returns_frontend_compatible_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "album_state.json"
            state_file.write_text(json.dumps(sample_album_state()), encoding="utf-8")

            with patch.dict(
                "os.environ",
                {
                    "ALBUM_STATE_BACKEND": "json",
                    "STATE_FILE": str(state_file),
                },
            ):
                client = TestClient(create_app())
                response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "last_checked",
                "albums_in_progress",
                "completed_albums",
                "most_recently_listened",
            },
        )
        album = payload["completed_albums"]["Artist - Finished Album"]
        self.assertEqual(album["artist"], "Artist")
        self.assertEqual(album["name"], "Finished Album")
        self.assertEqual(album["listen_history"], ["2026-04-18T15:45:00.000Z"])
        self.assertEqual(album["release_year"], 2026)
        self.assertEqual(album["tracklist"][0]["title"], "Opening Track")
        self.assertEqual(album["tags"], ["indie"])
        self.assertEqual(album["genres"], ["rock"])
        self.assertEqual(album["image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["source"], "musicbrainz")

    def test_album_state_endpoint_returns_empty_state_when_file_is_missing(self):
        with patch.dict(
            "os.environ",
            {
                "ALBUM_STATE_BACKEND": "json",
                "STATE_FILE": "/tmp/missing-album-state.json",
            },
        ):
            client = TestClient(create_app())
            response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "last_checked": None,
                "albums_in_progress": {},
                "completed_albums": {},
                "most_recently_listened": [],
            },
        )

    def test_album_state_endpoint_fills_missing_album_identity_from_key(self):
        state = sample_album_state()
        state["completed_albums"]["Soft Soundscapes - River"] = {
            "listen_history": ["2026-04-11T22:44:13.553Z"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "album_state.json"
            state_file.write_text(json.dumps(state), encoding="utf-8")

            with patch.dict(
                "os.environ",
                {
                    "ALBUM_STATE_BACKEND": "json",
                    "STATE_FILE": str(state_file),
                },
            ):
                client = TestClient(create_app())
                response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        album = response.json()["completed_albums"]["Soft Soundscapes - River"]
        self.assertEqual(album["artist"], "Soft Soundscapes")
        self.assertEqual(album["name"], "River")
        self.assertEqual(album["source"], "unknown")

    def test_album_state_endpoint_reads_from_sqlite_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_schema(database_url)
            session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())

            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": database_url,
                },
            ):
                client = TestClient(create_app())
                response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["completed_albums"]["Artist - Finished Album"]["name"],
            "Finished Album",
        )

    def test_album_state_endpoint_returns_local_artwork_url_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_schema(database_url)
            session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())
                album = session.scalars(select(Album)).one()
                album.local_image_path = "artwork/release-group-mbid.jpg"
                session.commit()

            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": database_url,
                    "MEDIA_DIR": temp_dir,
                },
            ):
                client = TestClient(create_app())
                response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        album = response.json()["completed_albums"]["Artist - Finished Album"]
        self.assertEqual(album["image_url"], "/media/artwork/release-group-mbid.jpg")
        self.assertEqual(album["remote_image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["local_image_path"], "artwork/release-group-mbid.jpg")


if __name__ == "__main__":
    unittest.main()
