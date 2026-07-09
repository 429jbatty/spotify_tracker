import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album, AlbumListen, User, UserAlbum
from one_time_scripts import _audit_credit_intelligence as audit


class CreditIntelligenceAuditScriptTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _seed_credit_fixture(self, session):
        user = User(slug="listener", display_name="Listener", is_active=True)
        other_user = User(slug="other", display_name="Other Listener", is_active=True)
        session.add_all([user, other_user])
        session.flush()

        credited = Album(
            album_key="artist-one-credited-album",
            artist="Artist One",
            name="Credited Album",
            metadata_json={
                "tracklist": [
                    {
                        "title": "One",
                        "credits": [
                            ["Recurring Producer", "producer", ""],
                            ["Session Guitarist", "guitar", ""],
                        ],
                    },
                    {
                        "title": "Two",
                        "credits": [
                            ["Recurring Producer", "producer", ""],
                            ["Noisy Assistant", "assistant engineer", ""],
                        ],
                    },
                ]
            },
        )
        second = Album(
            album_key="artist-two-second-album",
            artist="Artist Two",
            name="Second Album",
            metadata_json={
                "tracklist": [
                    {
                        "title": "One",
                        "credits": [
                            ["Recurring Producer", "producer", ""],
                            ["Writer", "work composer", ""],
                        ],
                    }
                ]
            },
        )
        no_tracklist = Album(
            album_key="artist-three-no-tracklist",
            artist="Artist Three",
            name="No Tracklist",
            metadata_json={},
        )
        no_credits = Album(
            album_key="artist-four-no-credits",
            artist="Artist Four",
            name="No Credits",
            metadata_json={"tracklist": [{"title": "Silent", "credits": []}]},
        )
        session.add_all([credited, second, no_tracklist, no_credits])
        session.flush()

        for album in [credited, second, no_tracklist, no_credits]:
            session.add(UserAlbum(user_id=user.id, album_id=album.id))
        session.add(UserAlbum(user_id=other_user.id, album_id=credited.id))
        session.add_all(
            [
                AlbumListen(
                    user_id=user.id,
                    album_id=credited.id,
                    listened_at="2026-01-01T00:00:00Z",
                    source="test",
                ),
                AlbumListen(
                    user_id=user.id,
                    album_id=credited.id,
                    listened_at="2026-01-02T00:00:00Z",
                    source="test",
                ),
                AlbumListen(
                    user_id=user.id,
                    album_id=second.id,
                    listened_at="2026-01-03T00:00:00Z",
                    source="test",
                ),
            ]
        )
        session.commit()

    def test_parse_credit_handles_existing_tuple_like_shape(self):
        credit = audit.parse_credit(["Producer One", "producer", "co"])

        self.assertEqual(credit.name, "Producer One")
        self.assertEqual(credit.role, "producer")
        self.assertEqual(credit.attributes, "co")
        self.assertEqual(credit.identity_key, "producer one")

    def test_parse_credit_handles_enriched_object_shape(self):
        credit = audit.parse_credit(
            {
                "name": "Producer One",
                "role": "producer",
                "attributes": ["co", "additional"],
                "artist_mbid": "artist-1",
                "source_scope": "recording",
            }
        )

        self.assertEqual(credit.name, "Producer One")
        self.assertEqual(credit.role, "producer")
        self.assertEqual(credit.attributes, "co, additional")
        self.assertEqual(credit.identity_key, "producer one")

    def test_build_user_report_summarizes_coverage_roles_and_recurrence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_credit_fixture(session)

            with session_factory() as session:
                reports = audit.build_user_reports(session, user_slug="listener")

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report.album_count, 4)
        self.assertEqual(report.albums_with_tracklist, 3)
        self.assertEqual(report.albums_with_credits, 2)
        self.assertEqual(report.total_credit_count, 6)
        self.assertEqual(report.name_only_credit_count, 6)
        self.assertEqual(dict(report.role_bucket_counts)["producer"], 3)
        self.assertEqual(dict(report.role_bucket_counts)["writer_composer"], 1)
        self.assertEqual(dict(report.noisy_role_candidates)["assistant engineer"], 1)
        self.assertEqual(report.albums_without_tracklist[0].name, "No Tracklist")
        self.assertEqual(report.albums_without_credits[0].name, "No Credits")

        top = report.recurrence[0]
        self.assertEqual(top.name, "Recurring Producer")
        self.assertEqual(top.distinct_album_count, 2)
        self.assertEqual(top.total_credit_count, 3)
        self.assertEqual(top.total_listen_count, 3)

    def test_report_generation_does_not_mutate_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_credit_fixture(session)

            with session_factory() as session:
                before = session.scalar(select(func.count(Album.id)))
                audit.build_user_reports(session, user_slug="listener")
                after = session.scalar(select(func.count(Album.id)))

        self.assertEqual(before, after)

    def test_text_report_labels_audit_only_identity_and_phase_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_credit_fixture(session)

            with session_factory() as session:
                text = audit.format_report(audit.build_user_reports(session))

        self.assertIn("Draft recurrence list (audit-only, normalized-name identity)", text)
        self.assertIn("Initial role bucket mapping", text)
        self.assertIn("Representative albums for possible later selective refresh", text)
        self.assertIn("Phase 1A decision gate", text)


if __name__ == "__main__":
    unittest.main()
