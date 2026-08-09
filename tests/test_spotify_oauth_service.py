import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from spotipy.exceptions import SpotifyException
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.repositories.user_repository import UserRepository
from backend.app.models import SpotifyOAuthState
from backend.app.services import auth_service
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


class FakeSpotifyUnregisteredUser:
    def __init__(self, auth):
        self.auth = auth

    def current_user(self):
        raise SpotifyException(
            403,
            -1,
            "The user is not registered for this application. "
            "Please check your settings on https://developer.spotify.com/dashboard.",
        )


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
                account = auth_service.create_account(
                    session,
                    email="friend@example.com",
                    password="correct-horse-battery-staple",
                )
                user = UserRepository(session).create_user(
                    slug="friend",
                    display_name="Friend",
                    owner_account_id=account.id,
                )
                user_id = user.id
                session.add(
                    SpotifyOAuthState(
                        user_id=user.id,
                        account_id=account.id,
                        state_hash=spotify_oauth_service._state_hash("callback-state"),
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
                session.commit()

            with session_factory() as session:
                with patch.object(spotify_oauth_service, "_oauth", return_value=FakeOAuth()):
                    with patch.object(spotify_oauth_service, "Spotify", FakeSpotify):
                        user_slug = spotify_oauth_service.connect_user_from_callback(
                            session,
                            code="callback-code",
                            state="callback-state",
                        )
                credentials = SpotifyCredentialsRepository(session).get_for_user(user_id)

        self.assertEqual(user_slug, "friend")
        self.assertEqual(credentials.refresh_token, "refresh-token")
        self.assertEqual(credentials.spotify_user_id, "spotify-user-id")
        self.assertEqual(credentials.scope, "user-read-recently-played")

    def test_callback_returns_friendly_error_for_unregistered_spotify_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_schema(database_url)
            session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )

            with session_factory() as session:
                account = auth_service.create_account(
                    session,
                    email="friend@example.com",
                    password="correct-horse-battery-staple",
                )
                user = UserRepository(session).create_user(
                    slug="friend",
                    display_name="Friend",
                    owner_account_id=account.id,
                )
                session.add(
                    SpotifyOAuthState(
                        user_id=user.id,
                        account_id=account.id,
                        state_hash=spotify_oauth_service._state_hash("callback-state"),
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
                session.commit()

            with session_factory() as session:
                with patch.object(spotify_oauth_service, "_oauth", return_value=FakeOAuth()):
                    with patch.object(
                        spotify_oauth_service,
                        "Spotify",
                        FakeSpotifyUnregisteredUser,
                    ):
                        with self.assertRaises(LookupError) as exc:
                            spotify_oauth_service.connect_user_from_callback(
                                session,
                                code="callback-code",
                                state="callback-state",
                            )

        self.assertIn("not allowed to use the app yet", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
