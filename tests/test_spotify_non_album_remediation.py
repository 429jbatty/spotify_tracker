import tempfile
import unittest
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import (
    Album,
    AlbumListen,
    ImportedListeningEvent,
    ImportSession,
    SpotifyStreamingEvent,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.spotify_catalog_service import SpotifyCatalogTrack
from one_time_scripts import remediate_spotify_non_album_imports as remediation


class SpotifyNonAlbumRemediationTests(unittest.TestCase):
    def _session_factory(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _seed_spotify_import_listen(self, session):
        repository = SqliteStateRepository(session)
        created = repository.create_completed_album(
            {
                "artist": "White Noise Artist",
                "name": "White Noise Single",
                "source": "musicbrainz",
                "entry_source": "spotify_import",
            },
            listen_date="2026-02-02T02:45:00Z",
        )
        import_session = ImportSession(
            user_id=repository.user.id,
            source="spotify_import",
            status="completed",
            started_at="2026-02-02T03:00:00Z",
            completed_at="2026-02-02T03:01:00Z",
            summary_json={},
        )
        session.add(import_session)
        session.flush()
        raw_event = SpotifyStreamingEvent(
            user_id=repository.user.id,
            import_session_id=import_session.id,
            event_fingerprint="raw-fingerprint",
            played_at="2026-02-02T02:45:00Z",
            ms_played=180000,
            spotify_track_uri="spotify:track:white-noise-track",
            spotify_track_id="white-noise-track",
            track_name="White Noise",
            artist_name="White Noise Artist",
            album_name="White Noise Single",
            raw_payload={},
        )
        session.add(raw_event)
        session.flush()
        imported = ImportedListeningEvent(
            user_id=repository.user.id,
            import_session_id=import_session.id,
            album_id=created["id"],
            source="spotify_import",
            event_fingerprint="imported-fingerprint",
            candidate_key="candidate-key",
            listened_at="2026-02-02T02:45:00Z",
            artist="White Noise Artist",
            album="White Noise Single",
            track="1 unique Spotify tracks",
            source_label="spotify_import",
            match_status="processed_album_listen",
            match_confidence=100,
            raw_payload={"_spotify_streaming_event_ids": [raw_event.id]},
        )
        session.add(imported)
        session.commit()
        return created["id"], imported.id

    def _resolver(self, album_type):
        def resolve(track_uris):
            return {
                uri: SpotifyCatalogTrack(
                    track_uri=uri,
                    track_id="white-noise-track",
                    track_name="White Noise",
                    album_id="spotify-white-noise-single",
                    album_name="White Noise Single",
                    album_artist_name="White Noise Artist",
                    album_total_tracks=1,
                    album_type=album_type,
                    disc_number=1,
                    track_number=1,
                    album_images=[],
                    album_release_date=None,
                    raw_payload={},
                )
                for uri in track_uris
            }

        return resolve

    def test_audit_reports_non_album_import_without_mutating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                album_id, _ = self._seed_spotify_import_listen(session)
                findings = remediation.audit_spotify_non_album_imports(
                    session,
                    resolve_tracks_by_uri=self._resolver("single"),
                )
                listen_count = session.query(AlbumListen).count()
                album = session.get(Album, album_id)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].action, "remove")
        self.assertEqual(findings[0].spotify_album_types, "single")
        self.assertEqual(listen_count, 1)
        self.assertIsNotNone(album)

    def test_apply_removes_bad_listen_and_preserves_raw_audit_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                album_id, imported_id = self._seed_spotify_import_listen(session)
                findings = remediation.audit_spotify_non_album_imports(
                    session,
                    resolve_tracks_by_uri=self._resolver("single"),
                )
                deleted = remediation.apply_spotify_non_album_remediation(session, findings)
                imported = session.get(ImportedListeningEvent, imported_id)
                album = session.get(Album, album_id)
                raw_count = session.query(SpotifyStreamingEvent).count()
                session_count = session.query(ImportSession).count()
                listen_count = session.query(AlbumListen).count()

        self.assertEqual(deleted, 1)
        self.assertEqual(listen_count, 0)
        self.assertEqual(imported.match_status, remediation.NON_ALBUM_STATUS)
        self.assertIsNone(imported.album_id)
        self.assertEqual(raw_count, 1)
        self.assertEqual(session_count, 1)
        self.assertIsNone(album)

    def test_audit_keeps_spotify_albums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_factory = self._session_factory(temp_dir)
            with session_factory() as session:
                self._seed_spotify_import_listen(session)
                findings = remediation.audit_spotify_non_album_imports(
                    session,
                    resolve_tracks_by_uri=self._resolver("album"),
                )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].action, "keep")


if __name__ == "__main__":
    unittest.main()
