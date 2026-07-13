import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album, AlbumCreditFact, AlbumListen
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository


def sample_album_state():
    return {
        "last_checked": "2026-04-18T16:14:25.872Z",
        "albums_in_progress": {
            "spotify-album-id": {
                "album_name": "Album In Progress",
                "artist": "Artist",
                "total_tracks": 10,
                "played_tracks": ["track-1", "track-2"],
                "first_played": "2026-04-18T15:00:00.000Z",
                "last_played": "2026-04-18T15:08:00.000Z",
                "completion_logged": False,
            }
        },
        "completed_albums": {
            "Artist - Finished Album": {
                "artist": "Artist",
                "name": "Finished Album",
                "artist_mbid": "artist-mbid",
                "release_group_mbid": "release-group-mbid",
                "release_mbid": "release-mbid",
                "label": "Label",
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
                "listen_history": [
                    "2026-04-18T15:45:00.000Z",
                    "2026-04-18T16:45:00.000Z",
                ],
            },
            "Sparse Artist - Sparse Album": {
                "listen_history": ["2026-04-17T15:45:00.000Z"],
            },
        },
        "most_recently_listened": ["Artist - Finished Album"],
    }


class SqliteStateRepositoryTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_path = Path(temp_dir) / "tracker.sqlite"
        database_url = f"sqlite:///{database_path}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_import_and_load_album_state_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())
                loaded = repository.load_album_state()

        self.assertEqual(loaded["last_checked"], "2026-04-18T16:14:25.872Z")
        self.assertEqual(
            loaded["albums_in_progress"]["spotify-album-id"]["played_tracks"],
            ["track-1", "track-2"],
        )

        album = loaded["completed_albums"]["Artist - Finished Album"]
        self.assertEqual(album["artist"], "Artist")
        self.assertEqual(album["name"], "Finished Album")
        self.assertEqual(album["release_group_mbid"], "release-group-mbid")
        self.assertEqual(album["image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["remote_image_url"], "https://example.test/cover.jpg")
        self.assertIsNone(album["local_image_path"])
        self.assertEqual(album["tracklist"][0]["title"], "Opening Track")
        self.assertEqual(
            album["listen_history"],
            ["2026-04-18T15:45:00.000Z", "2026-04-18T16:45:00.000Z"],
        )
        self.assertEqual(album["your_tags"], [])
        self.assertIsNone(album["rating"])
        self.assertIsNone(album["notes"])
        self.assertEqual(loaded["most_recently_listened"][0], "Artist - Finished Album")

    def test_import_is_idempotent_for_albums_and_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())
                repository.import_album_state(sample_album_state())

                album_count = len(session.scalars(select(Album)).all())
                listen_count = len(session.scalars(select(AlbumListen)).all())

        self.assertEqual(album_count, 2)
        self.assertEqual(listen_count, 3)

    def test_import_projects_credit_facts_from_persisted_album_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())
                repository.import_album_state(sample_album_state())

                facts = session.scalars(
                    select(AlbumCreditFact).order_by(AlbumCreditFact.person_name)
                ).all()

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].person_name, "Producer")
        self.assertEqual(facts[0].raw_role, "producer")
        self.assertEqual(facts[0].track_count, 1)

    def test_sparse_album_identity_is_filled_from_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.import_album_state(sample_album_state())
                loaded = repository.load_album_state()

        album = loaded["completed_albums"]["Sparse Artist - Sparse Album"]
        self.assertEqual(album["artist"], "Sparse Artist")
        self.assertEqual(album["name"], "Sparse Album")
        self.assertEqual(album["source"], "unknown")

    def test_save_album_state_removes_stale_albums_listens_and_in_progress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            updated_state = sample_album_state()
            del updated_state["completed_albums"]["Sparse Artist - Sparse Album"]
            updated_state["completed_albums"]["Artist - Finished Album"][
                "listen_history"
            ] = ["2026-04-18T16:45:00.000Z"]
            updated_state["albums_in_progress"] = {}

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                repository.save_album_state(updated_state)
                loaded = repository.load_album_state()

                album_count = len(session.scalars(select(Album)).all())
                listen_count = len(session.scalars(select(AlbumListen)).all())

        self.assertEqual(album_count, 1)
        self.assertEqual(listen_count, 1)
        self.assertNotIn("Sparse Artist - Sparse Album", loaded["completed_albums"])
        self.assertEqual(loaded["albums_in_progress"], {})
        self.assertEqual(
            loaded["completed_albums"]["Artist - Finished Album"]["listen_history"],
            ["2026-04-18T16:45:00.000Z"],
        )

    def test_save_album_state_removes_credit_facts_for_unowned_stale_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            updated_state = sample_album_state()
            del updated_state["completed_albums"]["Artist - Finished Album"]

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                repository.save_album_state(updated_state)

                album_count = len(session.scalars(select(Album)).all())
                credit_fact_count = len(session.scalars(select(AlbumCreditFact)).all())

        self.assertEqual(album_count, 1)
        self.assertEqual(credit_fact_count, 0)

    def test_replace_completed_album_metadata_preserves_listens_and_renames_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                new_key = repository.replace_completed_album_metadata(
                    "Artist - Finished Album",
                    {
                        "artist": "Artist",
                        "name": "Canonical Album",
                        "release_year": 2027,
                        "source": "musicbrainz",
                    },
                )
                loaded = repository.load_album_state()

                album_count = len(session.scalars(select(Album)).all())
                listen_count = len(session.scalars(select(AlbumListen)).all())

        self.assertEqual(new_key, "Artist - Canonical Album")
        self.assertEqual(album_count, 2)
        self.assertEqual(listen_count, 3)
        self.assertNotIn("Artist - Finished Album", loaded["completed_albums"])
        self.assertEqual(
            loaded["completed_albums"]["Artist - Canonical Album"]["listen_history"],
            ["2026-04-18T15:45:00.000Z", "2026-04-18T16:45:00.000Z"],
        )
        self.assertEqual(
            loaded["completed_albums"]["Artist - Canonical Album"]["release_year"],
            2027,
        )

    def test_replacing_metadata_replaces_existing_credit_facts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                repository.replace_completed_album_metadata(
                    "Artist - Finished Album",
                    {
                        "artist": "Artist",
                        "name": "Finished Album",
                        "source": "musicbrainz",
                        "tracklist": [
                            {
                                "position": "1",
                                "title": "Replacement Track",
                                "credits": [["New Producer", "producer", ""]],
                            }
                        ],
                    },
                )
                facts = session.scalars(
                    select(AlbumCreditFact).order_by(AlbumCreditFact.person_name)
                ).all()

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].person_name, "New Producer")
        self.assertEqual(facts[0].raw_role, "producer")

    def test_find_completed_album_key_supports_exact_and_casefolded_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())

                exact = repository.find_completed_album_key(
                    artist="Artist",
                    album="Finished Album",
                )
                casefolded = repository.find_completed_album_key(
                    artist="artist",
                    album="finished album",
                )

        self.assertEqual(exact, "Artist - Finished Album")
        self.assertEqual(casefolded, "Artist - Finished Album")

    def test_save_album_state_preserves_existing_local_image_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            updated_state = sample_album_state()
            updated_state["completed_albums"]["Artist - Finished Album"][
                "image_url"
            ] = "https://example.test/new-cover.jpg"

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())

                album = session.scalars(
                    select(Album).where(Album.album_key == "Artist - Finished Album")
                ).one()
                album.local_image_path = "artwork/release-group-mbid.jpg"
                session.commit()

                repository.save_album_state(updated_state)
                loaded = repository.load_album_state()

        album = loaded["completed_albums"]["Artist - Finished Album"]
        self.assertEqual(album["image_url"], "/media/artwork/release-group-mbid.jpg")
        self.assertEqual(
            album["remote_image_url"],
            "https://example.test/new-cover.jpg",
        )
        self.assertEqual(album["local_image_path"], "artwork/release-group-mbid.jpg")

    def test_update_user_album_tags_persists_per_user_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                album_id = repository.load_album_state()["completed_albums"][
                    "Artist - Finished Album"
                ]["id"]

                updated = repository.update_user_album_tags(
                    album_id,
                    ["atmospheric", "cohesive"],
                )

        self.assertEqual(updated["your_tags"], ["atmospheric", "cohesive"])

    def test_update_user_album_feedback_persists_rating_and_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())
                album_id = repository.load_album_state()["completed_albums"][
                    "Artist - Finished Album"
                ]["id"]

                updated = repository.update_user_album_feedback(
                    album_id,
                    rating=8,
                    notes="Huge low end and great pacing.",
                )

        self.assertEqual(updated["rating"], 8)
        self.assertEqual(updated["notes"], "Huge low end and great pacing.")

    def test_replace_completed_album_metadata_preserves_existing_local_image_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)

            with session_factory() as session:
                repository = SqliteStateRepository(session)
                repository.save_album_state(sample_album_state())

                album = session.scalars(
                    select(Album).where(Album.album_key == "Artist - Finished Album")
                ).one()
                album.local_image_path = "artwork/release-group-mbid.jpg"
                session.commit()

                repository.replace_completed_album_metadata(
                    "Artist - Finished Album",
                    {
                        "artist": "Artist",
                        "name": "Finished Album",
                        "image_url": "https://example.test/new-cover.jpg",
                        "source": "musicbrainz",
                    },
                )
                loaded = repository.load_album_state()

        album = loaded["completed_albums"]["Artist - Finished Album"]
        self.assertEqual(album["image_url"], "/media/artwork/release-group-mbid.jpg")
        self.assertEqual(
            album["remote_image_url"],
            "https://example.test/new-cover.jpg",
        )
        self.assertEqual(album["local_image_path"], "artwork/release-group-mbid.jpg")


if __name__ == "__main__":
    unittest.main()
