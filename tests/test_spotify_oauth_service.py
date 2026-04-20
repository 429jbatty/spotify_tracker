import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.repositories.user_repository import UserRepository
from backend.app.services import spotify_oauth_service


class FakeOAuth:
    def get_access_token(self, code=None, as_dict=True, check_cache=True):
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "scope": "user-read-recently-played",
        }


class FakeSpotify:
    def __init__(self, auth):
        self.auth = auth

    def current_user(self):
        return {"id": "spotify-user-id"}


class SpotifyOAuthServiceTests(unittest.TestCase):
    def test_callback_stores_user_spotify_credentials(self):
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
                user_id = user.id

            with session_factory() as session:
                with patch.object(spotify_oauth_service, "_oauth", return_value=FakeOAuth()):
                    with patch.object(spotify_oauth_service, "Spotify", FakeSpotify):
                        user_slug = spotify_oauth_service.connect_user_from_callback(
                            session,
                            code="callback-code",
                            state="friend",
                        )
                credentials = SpotifyCredentialsRepository(session).get_for_user(user_id)

        self.assertEqual(user_slug, "friend")
        self.assertEqual(credentials.refresh_token, "refresh-token")
        self.assertEqual(credentials.spotify_user_id, "spotify-user-id")
        self.assertEqual(credentials.scope, "user-read-recently-played")


if __name__ == "__main__":
    unittest.main()
