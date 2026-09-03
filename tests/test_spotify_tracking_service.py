import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services import spotify_tracking_service


class FakeSpotifyAPI:
    def __init__(self, credentials):
        self.credentials = credentials

    def fetch_recent_tracks(self, after_timestamp=None):
        return [
            {
                "track_spid": "track-1",
                "track_name": "Track 1",
                "album_id": "spotify-album-id",
                "album_name": "Completed Album",
                "artist": "Artist",
                "played_at": "2026-04-19T10:00:00.000Z",
            },
            {
                "track_spid": "track-2",
                "track_name": "Track 2",
                "album_id": "spotify-album-id",
                "album_name": "Completed Album",
                "artist": "Artist",
                "played_at": "2026-04-19T10:03:00.000Z",
            },
        ]

    def fetch_album_metadata(self, album_id):
        return {"album_type": "album", "total_tracks": 2}


class SpotifyTrackingServiceTests(unittest.TestCase):
    def test_run_tracking_for_user_updates_user_scoped_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_schema(database_url)
            session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )
            with session_factory() as session:
                user = UserRepository(session).create_user(
                    slug="friend",
                    display_name="Friend",
                )
                user.spotify_sync_enabled = True
                user_id = user.id
                SpotifyCredentialsRepository(session).upsert_credentials(
                    user_id=user_id,
                    refresh_token="refresh-token",
                )

            with patch.dict("os.environ", {"DATABASE_URL": database_url}):
                with patch.object(spotify_tracking_service, "SpotifyAPI", FakeSpotifyAPI):
                    with patch(
                        "tracking.meta.get_album_metadata",
                        return_value={
                            "artist": "Artist",
                            "name": "Completed Album",
                            "source": "musicbrainz",
                        },
                    ):
                        result = spotify_tracking_service.run_tracking_for_user("friend")

            with session_factory() as session:
                loaded = SqliteStateRepository(
                    session,
                    user_slug="friend",
                ).load_album_state()
                credentials = SpotifyCredentialsRepository(session).get_for_user(user_id)

        self.assertEqual(result["tracks_fetched"], 2)
        self.assertEqual(result["completed_albums"], 1)
        self.assertEqual(loaded["last_checked"], "2026-04-19T10:03:00.000Z")
        self.assertEqual(loaded["albums_in_progress"], {})
        self.assertEqual(
            loaded["completed_albums"]["Artist - Completed Album"]["listen_history"],
            ["2026-04-19T10:03:00.000Z"],
        )
        self.assertIsNotNone(credentials.last_successful_sync_at)


if __name__ == "__main__":
    unittest.main()
