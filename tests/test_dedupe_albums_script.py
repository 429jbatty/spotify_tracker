import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from tests.database_helpers import create_schema
from backend.app.database.models import Album, UserAlbum
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.album_state import AlbumStateRepository
from one_time_scripts import _dedupe_albums as dedupe


def duplicate_state():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {
            "Artist A - First Copy": {
                "artist": "Artist A",
                "name": "First Copy",
                "release_group_mbid": "rg-1",
                "source": "musicbrainz",
                "listen_history": ["2026-04-01T10:00:00.000Z"],
            },
            "Artist A - Second Copy": {
                "artist": "Artist A",
                "name": "Second Copy",
                "release_group_mbid": "rg-1",
                "source": "manual",
                "listen_history": ["2026-04-02T10:00:00.000Z"],
            },
            "Beyonce - Lemonade": {
                "artist": "Beyonce",
                "name": "Lemonade",
                "source": "manual",
                "listen_history": ["2026-04-03T10:00:00.000Z"],
            },
            "Beyoncé - Lemonade": {
                "artist": "Beyoncé",
                "name": "Lemonade",
                "source": "manual",
                "listen_history": ["2026-04-04T10:00:00.000Z"],
            },
            "The Beatles - Revolver": {
                "artist": "The Beatles",
                "name": "Revolver",
                "source": "manual",
                "listen_history": ["2026-04-05T10:00:00.000Z"],
            },
            "Beatles - Revolver": {
                "artist": "Beatles",
                "name": "Revolver",
                "source": "manual",
                "listen_history": ["2026-04-06T10:00:00.000Z"],
            },
            "Alvvays - Alvvays": {
                "artist": "Alvvays",
                "name": "Alvvays",
                "release_group_mbid": "rg-alvvays",
                "source": "musicbrainz",
                "listen_history": [],
            },
            "Alvvays - Antisocialites": {
                "artist": "Alvvays",
                "name": "Antisocialites",
                "release_group_mbid": "rg-antisocialites",
                "source": "musicbrainz",
                "listen_history": [],
            },
            "BROCKHAMPTON - SATURATION": {
                "artist": "BROCKHAMPTON",
                "name": "SATURATION",
                "release_group_mbid": "rg-saturation",
                "source": "musicbrainz",
                "listen_history": [],
            },
            "BROCKHAMPTON - SATURATION II": {
                "artist": "BROCKHAMPTON",
                "name": "SATURATION II",
                "release_group_mbid": "rg-saturation-ii",
                "source": "musicbrainz",
                "listen_history": [],
            },
        },
        "most_recently_listened": [],
    }


class DedupeAlbumsScriptTests(unittest.TestCase):
    def _session_factory(self, temp_dir, state=None):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            repository = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            AlbumStateRepository(session, repository.user).replace(state or duplicate_state())
        return session_factory

    def test_find_duplicate_groups_reports_safe_and_review_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                groups = dedupe.find_duplicate_groups(session)

        reasons = [group.reason for group in groups]
        self.assertIn("near_normalized_artist_album", reasons)

        safe_reasons = {group.reason for group in groups if group.safe_to_apply}
        self.assertEqual(
            safe_reasons,
            set(),
        )
        near_pairs = {
            frozenset((album.artist, album.name) for album in group.albums)
            for group in groups
            if group.reason == "near_normalized_artist_album"
        }
        self.assertIn(
            frozenset(
                {
                    ("The Beatles", "Revolver"),
                    ("Beatles", "Revolver"),
                }
            ),
            near_pairs,
        )
        self.assertNotIn(
            frozenset(
                {
                    ("Alvvays", "Alvvays"),
                    ("Alvvays", "Antisocialites"),
                }
            ),
            near_pairs,
        )
        self.assertNotIn(
            frozenset(
                {
                    ("BROCKHAMPTON", "SATURATION"),
                    ("BROCKHAMPTON", "SATURATION II"),
                }
            ),
            near_pairs,
        )

    def test_apply_preserves_conflicting_release_groups_with_matching_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            factory = self._session_factory(temp_dir)
            with factory() as session:
                repository = AlbumLibrary(session, UserRepository(session).ensure_default_user())
                for artist, mbid in [("Beyonce", "group-one"), ("Beyoncé", "group-two")]:
                    repository.add_album(
                        {"artist": artist, "name": "Record", "release_group_mbid": mbid},
                        listen_date="2026-04-01",
                    )
                before = AlbumStateRepository(session, repository.user).load()
                groups = dedupe.find_duplicate_groups(session)
                group = next(group for group in groups if group.reason == "exact_normalized_artist_album")
                self.assertFalse(group.safe_to_apply)
                self.assertEqual(dedupe.apply_duplicate_groups(repository, groups), [])
                self.assertEqual(AlbumStateRepository(session, repository.user).load(), before)

    def test_apply_checks_membership_before_merging_any_album_in_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            factory = self._session_factory(temp_dir)
            with factory() as session:
                repository = AlbumLibrary(session, UserRepository(session).ensure_default_user())
                other = UserRepository(session).create_user(slug="other", display_name="Other")
                # Older rows can have distinct keys for the same normalized identity.
                copies = []
                for title, owner in [("Pressing", repository.user), ("PRESSING", repository.user), ("pressing", other)]:
                    album = Album(album_key=f"A - {title}", artist="A", name=title)
                    session.add(album)
                    session.flush()
                    session.add(UserAlbum(user_id=owner.id, album_id=album.id))
                    copies.append(album)
                session.commit()
                groups = dedupe.find_duplicate_groups(session)
                before = AlbumStateRepository(session, repository.user).load()
                actions = dedupe.apply_duplicate_groups(repository, groups)
                self.assertEqual(len(actions), 1)
                self.assertIn("skipped", actions[0])
                self.assertEqual(AlbumStateRepository(session, repository.user).load(), before)

                session.add(UserAlbum(user_id=repository.user.id, album_id=copies[2].id))
                session.commit()
                other_repository = AlbumLibrary(session, UserRepository(session).require_user_by_slug("other"))
                other_before = AlbumStateRepository(session, other_repository.user).load()
                actions = dedupe.apply_duplicate_groups(repository, dedupe.find_duplicate_groups(session))
                self.assertEqual(len([action for action in actions if action.startswith("merged")]), 2)
                self.assertEqual(AlbumStateRepository(session, other_repository.user).load(), other_before)

    def test_dry_run_detection_does_not_mutate_albums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                before = len(AlbumStateRepository(session, UserRepository(session).ensure_default_user()).load()["completed_albums"])
                dedupe.find_duplicate_groups(session)
                after = len(AlbumStateRepository(session, UserRepository(session).ensure_default_user()).load()["completed_albums"])

        self.assertEqual(before, 8)
        self.assertEqual(after, 8)

    def test_apply_merges_only_safe_duplicate_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                repository = AlbumLibrary(session, UserRepository(session).ensure_default_user())
                groups = dedupe.find_duplicate_groups(session)
                actions = dedupe.apply_duplicate_groups(repository, groups)
                state = AlbumStateRepository(session, repository.user).load()

        self.assertEqual(len(actions), 0)
        self.assertIn("The Beatles - Revolver", state["completed_albums"])
        self.assertIn("Beatles - Revolver", state["completed_albums"])
        self.assertEqual(len(state["completed_albums"]), 8)

        merged_same_mbid = state["completed_albums"]["Artist A - First Copy"]
        self.assertEqual(
            merged_same_mbid["listen_history"],
            ["2026-04-01T10:00:00.000Z", "2026-04-02T10:00:00.000Z"],
        )

    def test_refresh_candidates_uses_low_confidence_safeguards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(
                temp_dir,
                state={
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Artist - Album": {
                            "artist": "Artist",
                            "name": "Album",
                            "source": "manual",
                            "listen_history": [],
                        }
                    },
                    "most_recently_listened": [],
                },
            )
            with session_factory() as session:
                repository = AlbumLibrary(session, UserRepository(session).ensure_default_user())
                album_id = next(iter(AlbumStateRepository(session, repository.user).load()["completed_albums"].values()))[
                    "id"
                ]
                with patch(
                    "one_time_scripts._dedupe_albums.metadata_refresh_service.refresh_album_record",
                    side_effect=dedupe.metadata_refresh_service.LowConfidenceMetadataError(
                        "low confidence"
                    ),
                ):
                    actions = dedupe.refresh_candidates(repository, [album_id])
                state = AlbumStateRepository(session, repository.user).load()

        self.assertEqual(state["completed_albums"]["Artist - Album"]["source"], "manual")
        self.assertIn("skipped", actions[0])
        self.assertIn("skipped_low_confidence", actions[0])


if __name__ == "__main__":
    unittest.main()
