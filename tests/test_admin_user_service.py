import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import (
    Album,
    AlbumInProgress,
    AlbumListen,
    User,
    UserAlbum,
    UserAppState,
    UserSpotifyCredentials,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import DEFAULT_USER_SLUG, UserRepository
from backend.app.services.admin_user_service import delete_user_by_slug


def sample_album_state():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Shared Album": {
                "artist": "Artist",
                "name": "Shared Album",
                "source": "manual",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            },
            "Solo Artist - Solo Album": {
                "artist": "Solo Artist",
                "name": "Solo Album",
                "source": "manual",
                "listen_history": ["2026-04-17T15:45:00.000Z"],
            },
        },
        "most_recently_listened": ["Artist - Shared Album"],
    }


class AdminUserServiceTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_path = Path(temp_dir) / "tracker.sqlite"
        database_url = f"sqlite:///{database_path}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_delete_user_removes_dependent_rows_and_orphaned_albums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                default_repo = SqliteStateRepository(session)
                default_repo.save_album_state(sample_album_state())

                friend = UserRepository(session).create_user(
                    slug="friend",
                    display_name="Friend",
                )
                friend_repo = SqliteStateRepository(session, user_slug=friend.slug)
                friend_repo.create_completed_album(
                    {
                        "artist": "Artist",
                        "name": "Shared Album",
                        "source": "manual",
                    },
                    listen_date="2026-04-19T15:45:00.000Z",
                )
                friend_repo.create_completed_album(
                    {
                        "artist": "Friend Artist",
                        "name": "Friend Only Album",
                        "source": "manual",
                    },
                    listen_date="2026-04-21T10:00:00.000Z",
                )
                friend_album_id = friend_repo.load_album_state()["completed_albums"][
                    "Artist - Shared Album"
                ]["id"]
                friend_repo.update_user_album_feedback(
                    friend_album_id,
                    rating=8,
                    notes="Friend note",
                )
                session.add(
                    AlbumInProgress(
                        user_id=friend.id,
                        spotify_album_id="spotify:album:friend",
                        album_name="In Progress",
                        artist="Friend Artist",
                        total_tracks=10,
                        played_tracks=["track-1"],
                        first_played="2026-04-20T10:00:00.000Z",
                        last_played="2026-04-20T10:10:00.000Z",
                    )
                )
                session.add(
                    UserAppState(user_id=friend.id, key="last_checked", value="2026-04-20")
                )
                session.add(
                    UserSpotifyCredentials(
                        user_id=friend.id,
                        refresh_token="refresh-token",
                    )
                )
                session.commit()

                shared_album_id = session.scalars(
                    select(Album.id).where(Album.album_key == "Artist - Shared Album")
                ).one()
                result = delete_user_by_slug(session, user_slug="friend")

                remaining_users = list(session.scalars(select(User.slug)))
                remaining_albums = list(session.scalars(select(Album.album_key)))
                shared_album_memberships = list(
                    session.scalars(
                        select(UserAlbum).where(UserAlbum.album_id == shared_album_id)
                    )
                )

        self.assertTrue(result.found)
        self.assertEqual(result.deleted_spotify_credentials, 1)
        self.assertGreaterEqual(result.deleted_album_listens, 2)
        self.assertGreaterEqual(result.deleted_user_albums, 2)
        self.assertEqual(result.deleted_albums_in_progress, 1)
        self.assertEqual(result.deleted_user_app_state, 1)
        self.assertEqual(result.deleted_users, 1)
        self.assertEqual(result.orphaned_albums_removed, 1)
        self.assertEqual(remaining_users, [DEFAULT_USER_SLUG])
        self.assertIn("Artist - Shared Album", remaining_albums)
        self.assertNotIn("Friend Artist - Friend Only Album", remaining_albums)
        self.assertEqual(len(shared_album_memberships), 1)

    def test_delete_user_refuses_default_user_without_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                SqliteStateRepository(session)

                with self.assertRaises(ValueError):
                    delete_user_by_slug(session, user_slug=DEFAULT_USER_SLUG)

    def test_delete_user_returns_not_found_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                SqliteStateRepository(session)
                result = delete_user_by_slug(session, user_slug="missing-user")

        self.assertFalse(result.found)


if __name__ == "__main__":
    unittest.main()
