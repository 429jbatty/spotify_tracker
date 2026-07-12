import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album, AlbumCreditFact
from backend.app.services import credit_fact_service


class CreditFactServiceTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _seed_albums(self, session):
        legacy = Album(
            album_key="Artist - Legacy",
            artist="Artist",
            name="Legacy",
            artist_mbid="artist-mbid",
            source="musicbrainz",
            entry_source="spotify_sync",
            metadata_json={
                "tracklist": [
                    {
                        "position": "1",
                        "title": "One",
                        "recording_mbid": "recording-1",
                        "credits": [
                            ["Producer One", "producer", ""],
                            ["Artist", "instrument", ""],
                        ],
                    },
                    {
                        "position": "2",
                        "title": "Two",
                        "recording_mbid": "recording-2",
                        "credits": [["Producer One", "producer", ""]],
                    },
                ]
            },
        )
        enriched = Album(
            album_key="Artist - Enriched",
            artist="Artist",
            name="Enriched",
            artist_mbid="artist-mbid",
            source="musicbrainz",
            entry_source="spotify_sync",
            metadata_json={
                "tracklist": [
                    {
                        "position": "1",
                        "title": "One",
                        "recording_mbid": "recording-3",
                        "credits": [
                            {
                                "name": "Producer Two",
                                "artist_mbid": "producer-two-mbid",
                                "role": "producer",
                                "raw_credit_type": "producer",
                                "attributes": ["co"],
                                "source_scope": "recording",
                                "identity_resolution": "mbid",
                                "ingestion_version": "musicbrainz_credit_v2",
                            }
                        ],
                    }
                ]
            },
        )
        session.add_all([legacy, enriched])
        session.commit()
        return legacy.id, enriched.id

    def test_rebuild_credit_facts_projects_legacy_and_enriched_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                legacy_id, enriched_id = self._seed_albums(session)

                result = credit_fact_service.rebuild_credit_facts(session)
                facts = session.scalars(
                    select(AlbumCreditFact).order_by(
                        AlbumCreditFact.album_id,
                        AlbumCreditFact.person_name,
                    )
                ).all()

        self.assertEqual(result.inserted_count, 3)
        self.assertEqual({fact.album_id for fact in facts}, {legacy_id, enriched_id})

        legacy_producer = next(
            fact for fact in facts if fact.person_name == "Producer One"
        )
        self.assertEqual(legacy_producer.person_key, "name:producer one")
        self.assertEqual(legacy_producer.identity_resolution, "normalized_name")
        self.assertEqual(
            legacy_producer.ingestion_version,
            credit_fact_service.LEGACY_CREDIT_INGESTION_VERSION,
        )
        self.assertEqual(legacy_producer.track_count, 2)
        self.assertEqual(legacy_producer.album_track_count, 2)
        self.assertEqual(legacy_producer.track_share, 1)
        self.assertIn("legacy_credit", legacy_producer.quality_flags_json)

        primary_artist = next(fact for fact in facts if fact.person_name == "Artist")
        self.assertEqual(primary_artist.role_bucket, "other")
        self.assertIn("generic_instrument", primary_artist.quality_flags_json)
        self.assertIn("primary_artist_candidate", primary_artist.quality_flags_json)

        enriched = next(fact for fact in facts if fact.person_name == "Producer Two")
        self.assertEqual(enriched.person_key, "mbid:producer-two-mbid")
        self.assertEqual(enriched.person_mbid, "producer-two-mbid")
        self.assertEqual(enriched.identity_resolution, "mbid")
        self.assertEqual(enriched.source_scope, "recording")
        self.assertEqual(enriched.recording_mbid, "recording-3")
        self.assertIn("enriched_credit", enriched.quality_flags_json)

    def test_rebuild_credit_facts_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_albums(session)

                first = credit_fact_service.rebuild_credit_facts(session)
                second = credit_fact_service.rebuild_credit_facts(session)
                facts = session.scalars(select(AlbumCreditFact)).all()

        self.assertEqual(first.inserted_count, 3)
        self.assertEqual(second.deleted_count, 3)
        self.assertEqual(second.inserted_count, 3)
        self.assertEqual(len(facts), 3)

    def test_rebuild_credit_facts_can_target_selected_albums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                legacy_id, _ = self._seed_albums(session)

                result = credit_fact_service.rebuild_credit_facts(
                    session,
                    album_ids=[legacy_id],
                )
                facts = session.scalars(select(AlbumCreditFact)).all()

        self.assertEqual(result.album_ids, [legacy_id])
        self.assertEqual(result.inserted_count, 2)
        self.assertEqual({fact.album_id for fact in facts}, {legacy_id})

    def test_rebuild_credit_facts_skips_malformed_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            engine = create_schema(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO albums (
                            album_key,
                            artist,
                            name,
                            source,
                            entry_source,
                            metadata_json
                        )
                        VALUES (
                            'Broken - Album',
                            'Broken',
                            'Album',
                            'musicbrainz',
                            'spotify_sync',
                            '{"tracklist": ['
                        )
                        """
                    )
                )

            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                result = credit_fact_service.rebuild_credit_facts(session)
                facts = session.scalars(select(AlbumCreditFact)).all()

        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(result.skipped_parse_error_count, 1)
        self.assertEqual(facts, [])


if __name__ == "__main__":
    unittest.main()
