import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album, AlbumListen, User, UserAlbum
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from one_time_scripts import _credit_refresh_experiment as experiment


class CreditRefreshExperimentScriptTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _add_album(
        self,
        session,
        user,
        *,
        album_key,
        artist,
        name,
        metadata_json,
        listen_count=0,
    ):
        album = Album(
            album_key=album_key,
            artist=artist,
            name=name,
            metadata_json=metadata_json,
        )
        session.add(album)
        session.flush()
        session.add(UserAlbum(user_id=user.id, album_id=album.id))
        for index in range(listen_count):
            session.add(
                AlbumListen(
                    user_id=user.id,
                    album_id=album.id,
                    listened_at=f"2026-01-{index + 1:02d}T00:00:00Z",
                    source="test",
                )
            )
        return album

    def _seed_fixture(self, session):
        user = User(slug="listener", display_name="Listener", is_active=True)
        session.add(user)
        session.flush()

        no_tracklist = self._add_album(
            session,
            user,
            album_key="artist-no-tracklist",
            artist="Artist",
            name="No Tracklist",
            metadata_json={},
            listen_count=3,
        )
        no_credits = self._add_album(
            session,
            user,
            album_key="artist-no-credits",
            artist="Artist",
            name="No Credits",
            metadata_json={"tracklist": [{"title": "Track", "credits": []}]},
            listen_count=2,
        )
        high_volume = self._add_album(
            session,
            user,
            album_key="artist-high-volume",
            artist="Artist",
            name="High Volume",
            metadata_json={
                "tracklist": [
                    {
                        "title": "Track",
                        "credits": [
                            [f"Person {index}", "producer", ""]
                            for index in range(25)
                        ],
                    }
                ]
            },
            listen_count=1,
        )
        covered = self._add_album(
            session,
            user,
            album_key="artist-covered",
            artist="Artist",
            name="Covered",
            metadata_json={
                "tracklist": [
                    {
                        "title": "Track",
                        "credits": [["Producer One", "producer", ""]],
                    }
                ]
            },
            listen_count=4,
        )
        session.commit()
        return {
            "no_tracklist": no_tracklist.id,
            "no_credits": no_credits.id,
            "high_volume": high_volume.id,
            "covered": covered.id,
        }

    def test_analyze_credit_quality_counts_legacy_and_enriched_credits(self):
        quality = experiment.analyze_credit_quality(
            {
                "tracklist": [
                    {
                        "title": "Track",
                        "credits": [
                            ["Legacy Producer", "producer", ""],
                            {
                                "name": "Enriched Producer",
                                "role": "producer",
                                "artist_mbid": "artist-1",
                                "source_scope": "recording",
                            },
                        ],
                    }
                ]
            }
        )

        self.assertEqual(quality.track_count, 1)
        self.assertEqual(quality.credit_count, 2)
        self.assertEqual(quality.legacy_credit_count, 1)
        self.assertEqual(quality.structured_credit_count, 1)
        self.assertEqual(quality.mbid_credit_count, 1)
        self.assertEqual(quality.scoped_credit_count, 1)

    def test_select_refresh_candidates_includes_representative_reasons(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_fixture(session)

            with session_factory() as session:
                candidates = experiment.select_refresh_candidates(
                    session,
                    "listener",
                    limit=4,
                )

        reasons = {candidate.reason for candidate in candidates}
        self.assertIn("no_tracklist", reasons)
        self.assertIn("tracklist_no_credits", reasons)
        self.assertIn("high_credit_volume", reasons)
        self.assertIn("high_listen_covered", reasons)

    def test_select_refresh_candidates_by_id_preserves_requested_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                ids = self._seed_fixture(session)

            with session_factory() as session:
                candidates = experiment.select_refresh_candidates_by_id(
                    session,
                    "listener",
                    [ids["covered"], ids["no_credits"]],
                )

        self.assertEqual(
            [candidate.album_id for candidate in candidates],
            [ids["covered"], ids["no_credits"]],
        )

    def test_dry_run_results_do_not_mutate_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_fixture(session)

            with session_factory() as session:
                candidates = experiment.select_refresh_candidates(
                    session,
                    "listener",
                    limit=2,
                )
                before = session.scalar(select(func.count(Album.id)))
                results = experiment.dry_run_results(candidates)
                after = session.scalar(select(func.count(Album.id)))

        self.assertEqual(before, after)
        self.assertEqual([result.status for result in results], ["dry_run_selected", "dry_run_selected"])

    def test_apply_refresh_experiment_uses_refresh_boundary_and_updates_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                ids = self._seed_fixture(session)

            with session_factory() as session:
                candidate = next(
                    candidate
                    for candidate in experiment.select_refresh_candidates(
                        session,
                        "listener",
                        limit=4,
                    )
                    if candidate.album_id == ids["covered"]
                )
                repository = SqliteStateRepository(session, user_slug="listener")
                refreshed = {
                    "artist": "Artist",
                    "name": "Covered",
                    "tracklist": [
                        {
                            "title": "Track",
                            "credits": [
                                {
                                    "name": "Producer One",
                                    "role": "producer",
                                    "artist_mbid": "artist-1",
                                    "source_scope": "recording",
                                    "attributes": [],
                                    "ingestion_version": "musicbrainz_credit_v2",
                                }
                            ],
                        }
                    ],
                    "source": "musicbrainz",
                }

                with patch(
                    "one_time_scripts._credit_refresh_experiment.metadata_refresh_service.refresh_album_record",
                    return_value=refreshed,
                ):
                    results = experiment.apply_refresh_experiment(repository, [candidate])

        self.assertEqual(results[0].status, "refreshed")
        self.assertEqual(results[0].before.legacy_credit_count, 1)
        self.assertEqual(results[0].after.structured_credit_count, 1)
        self.assertEqual(results[0].after.mbid_credit_count, 1)


if __name__ == "__main__":
    unittest.main()
