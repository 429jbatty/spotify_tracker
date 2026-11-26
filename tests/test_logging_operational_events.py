import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from structlog.testing import capture_logs

from spotify_manager import SpotifyAPI
from backend.app.services.imports.candidate_results import log_candidate_outcomes
from backend.app.services.imports.progress import empty_summary
from backend.app.services.imports.spotify_source import resolve_spotify_catalog_for_import
from backend.app.services.spotify_catalog_service import SpotifyCatalogUnavailable


class OperationalEventsTests(unittest.TestCase):
    def test_full_spotify_page_warns_only_when_watermark_is_outside_page(self):
        api = object.__new__(SpotifyAPI)
        api.sp = Mock()
        item = {"played_at": "2020-01-01T00:00:00Z", "track": {
            "id": "track", "name": "track", "album": {"id": "album", "name": "album", "artists": [{"name": "artist"}]},
        }}
        api.sp.current_user_recently_played.return_value = {"items": [item] * 50}
        with capture_logs() as events:
            tracks = api.fetch_recent_tracks("2019-01-01T00:00:00Z")
        self.assertEqual(len(tracks), 50)
        self.assertEqual(events[0]["event"], "spotify_recent_plays_page_full")
        self.assertEqual(events[0]["raw_play_count"], 50)
        self.assertEqual(events[0]["log_level"], "warning")
        with capture_logs() as events:
            self.assertEqual(api.fetch_recent_tracks("2021-01-01T00:00:00Z"), [])
        self.assertEqual(events, [])

    def test_catalog_unavailable_emits_fallback_with_distinct_units(self):
        session = Mock()
        rows = [
            SimpleNamespace(spotify_track_uri="spotify:track:one"),
            SimpleNamespace(spotify_track_uri="spotify:track:one"),
        ]
        repository = SimpleNamespace(user=SimpleNamespace(id=1))
        import_session = SimpleNamespace(id=2)
        summary = empty_summary()
        with patch("backend.app.services.imports.spotify_source.import_spotify", autospec=True) as spotify_rows, \
             patch("backend.app.services.imports.spotify_source.append_import_log"), \
             patch("backend.app.services.spotify_catalog_service.resolve_tracks_by_uri", side_effect=SpotifyCatalogUnavailable("offline")), \
             capture_logs() as events:
            spotify_rows.unresolved_catalog_rows.return_value = rows
            spotify_rows.fallback_count.return_value = 2
            resolve_spotify_catalog_for_import(session, repository, import_session, summary)
        event = next(event for event in events if event["event"] == "spotify_catalog_fallback")
        self.assertEqual(event["unique_track_ids"], 1)
        self.assertEqual(event["fallback_source_rows"], 2)
        self.assertEqual(event["log_level"], "warning")

    def test_catalog_resume_does_not_claim_missing_track_uris(self):
        session = Mock()
        # A resumed session can have already-processed unresolved track IDs;
        # the lookup query returns none because no IDs remain to be attempted.
        repository = SimpleNamespace(user=SimpleNamespace(id=1))
        import_session = SimpleNamespace(id=2)
        summary = empty_summary()
        with patch("backend.app.services.imports.spotify_source.import_spotify", autospec=True) as spotify_rows, capture_logs() as events:
            spotify_rows.unresolved_catalog_rows.return_value = []
            spotify_rows.fallback_count.return_value = 3
            resolve_spotify_catalog_for_import(session, repository, import_session, summary)
        self.assertEqual(events[0]["reason"], "no_unresolved_track_uris")
        self.assertEqual(events[0]["fallback_source_rows"], 3)

    def test_candidate_outcomes_count_sessions_and_label_subset(self):
        candidates = [SimpleNamespace(status="partial_listen"),
                      SimpleNamespace(status="partial_listen"),
                      SimpleNamespace(status="candidate_review")]
        with capture_logs() as events:
            log_candidate_outcomes(candidates, scope="resume_subset")
        event = events[0]
        self.assertEqual(event["candidate_scope"], "resume_subset")
        self.assertEqual(event["album_session_candidates"], 3)
        self.assertEqual(event["status_counts"], {"partial_listen": 2, "candidate_review": 1})


if __name__ == "__main__":
    unittest.main()
