import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
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
        },
        "most_recently_listened": [],
    }


class DedupeAlbumsScriptTests(unittest.TestCase):
    def _session_factory(self, temp_dir, state=None):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            repository = SqliteStateRepository(session)
            repository.save_album_state(state or duplicate_state())
        return session_factory

    def test_find_duplicate_groups_reports_safe_and_review_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                groups = dedupe.find_duplicate_groups(session)

        reasons = [group.reason for group in groups]
        self.assertIn("same_release_group_mbid", reasons)
        self.assertIn("exact_normalized_artist_album", reasons)
        self.assertIn("near_normalized_artist_album", reasons)

        safe_reasons = {group.reason for group in groups if group.safe_to_apply}
        self.assertEqual(
            safe_reasons,
            {"same_release_group_mbid", "exact_normalized_artist_album"},
        )

    def test_dry_run_detection_does_not_mutate_albums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                before = len(SqliteStateRepository(session).load_album_state()["completed_albums"])
                dedupe.find_duplicate_groups(session)
                after = len(SqliteStateRepository(session).load_album_state()["completed_albums"])

        self.assertEqual(before, 6)
        self.assertEqual(after, 6)

    def test_apply_merges_only_safe_duplicate_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                groups = dedupe.find_duplicate_groups(session)
                actions = dedupe.apply_duplicate_groups(repository, groups)
                state = repository.load_album_state()

        self.assertEqual(len(actions), 2)
        self.assertIn("The Beatles - Revolver", state["completed_albums"])
        self.assertIn("Beatles - Revolver", state["completed_albums"])
        self.assertEqual(len(state["completed_albums"]), 4)

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
                repository = SqliteStateRepository(session)
                album_id = next(iter(repository.load_album_state()["completed_albums"].values()))[
                    "id"
                ]
                with patch(
                    "one_time_scripts._dedupe_albums.metadata_refresh_service.refresh_album_record",
                    side_effect=dedupe.metadata_refresh_service.LowConfidenceMetadataError(
                        "low confidence"
                    ),
                ):
                    actions = dedupe.refresh_candidates(repository, [album_id])
                state = repository.load_album_state()

        self.assertEqual(state["completed_albums"]["Artist - Album"]["source"], "manual")
        self.assertIn("skipped", actions[0])
        self.assertIn("skipped_low_confidence", actions[0])


if __name__ == "__main__":
    unittest.main()
