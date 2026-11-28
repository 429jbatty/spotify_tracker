"""File-backed regressions: provider callbacks commit through independent sessions."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from threading import Barrier, Lock
import unittest
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.album_state import AlbumStateRepository, SpotifySyncConflict
from backend.app.database.repositories.spotify_credentials_repository import SpotifyCredentialsRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.services import spotify_tracking_service as service
from tests.database_helpers import create_schema


class SpotifySyncConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = create_schema(f"sqlite:///{Path(temporary.name) / 'sync.sqlite'}")
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.now = datetime.now(timezone.utc)
        self.old_listen = self.timestamp(-100)
        self.manual_listen = self.timestamp(-10)
        self.track_times = [self.timestamp(-2), self.timestamp(-1)]
        self.fetches = []
        self.on_fetch = lambda: None
        self.tracks = [self.track(index) for index in range(2)]
        for slug in ("listener", "other"):
            with self.sessions() as session:
                user = UserRepository(session).create_user(slug=slug, display_name=slug)
                user.spotify_sync_enabled = True
                SpotifyCredentialsRepository(session).upsert_credentials(
                    user_id=user.id, refresh_token="fixture-token",
                )
                AlbumLibrary(session, user).add_album(self.record("Existing"), self.old_listen)

        provider = self

        class Spotify:
            def fetch_recent_tracks(self, after_timestamp=None):
                provider.fetches.append(after_timestamp)
                provider.on_fetch()
                return [track for track in provider.tracks
                        if not after_timestamp or track["played_at"] > after_timestamp]

            def fetch_album_metadata(self, album_id):
                return {"album_type": "album", "total_tracks": 2}

        self.addCleanup(patch.stopall)
        patch.object(service, "SpotifyAPI", return_value=Spotify()).start()
        # Fail immediately if a test unexpectedly reaches the MusicBrainz boundary.
        patch("tracking.meta.get_album_metadata", side_effect=AssertionError("Unexpected metadata I/O")).start()
        patch.object(service, "_env_credentials", return_value={}).start()

    def timestamp(self, minutes):
        return (self.now + timedelta(minutes=minutes)).isoformat()

    def record(self, title):
        return {"artist": "Artist", "name": title, "source": "manual", "label": "Original"}

    def track(self, index, *, album_id="existing", title="Existing", minutes=None):
        return {
            "track_spid": f"track-{index}", "album_id": album_id,
            "album_name": title, "artist": "Artist",
            "played_at": self.track_times[index] if minutes is None else self.timestamp(minutes),
        }

    def run_sync(self, slug="listener"):
        return service.run_tracking_for_user(slug, open_session=self.sessions)

    def load(self, slug="listener"):
        with self.sessions() as session:
            user = UserRepository(session).require_user_by_slug(slug)
            return AlbumStateRepository(session, user).load()

    def credentials(self):
        with self.sessions() as session:
            user = UserRepository(session).require_user_by_slug("listener")
            credentials = SpotifyCredentialsRepository(session).get_for_user(user.id)
            return credentials.last_successful_sync_at, credentials.last_sync_error

    def test_manual_additions_listens_feedback_and_metadata_survive_provider_fetch(self):
        other_before = self.load("other")

        def write_during_fetch():
            self.on_fetch = lambda: None
            with self.sessions() as session:
                user = UserRepository(session).require_user_by_slug("listener")
                library = AlbumLibrary(session, user)
                existing = library.catalog.require_by_key("Artist - Existing")
                library.add_listen(existing.id, self.manual_listen)
                library.set_feedback(existing.id, rating=4, notes="Concurrent note")
                library.patch_metadata(existing.id, {"label": "Edited during fetch"})
                library.add_album(self.record("Manual"), self.manual_listen)

        self.on_fetch = write_during_fetch
        result = self.run_sync()
        state = self.load()
        existing = state["completed_albums"]["Artist - Existing"]
        self.assertEqual(existing["listen_history"],
                         [self.old_listen, self.manual_listen, self.track_times[-1]])
        self.assertEqual(existing["label"], "Edited during fetch")
        self.assertEqual((existing["rating"], existing["notes"]), (4, "Concurrent note"))
        self.assertEqual(state["completed_albums"]["Artist - Manual"]["listen_history"],
                         [self.manual_listen])
        self.assertEqual(self.fetches, [None, None])
        self.assertEqual(state["last_checked"], self.track_times[-1])
        self.assertEqual(state["albums_in_progress"], {})
        self.assertEqual(state["most_recently_listened"][0], "Artist - Existing")
        self.assertEqual(result, {"tracks_fetched": 2, "completed_albums": 1, "net_album_count_change": 0})
        self.assertIsNotNone(self.credentials()[0])
        # The manual metadata edit is shared; history and feedback are scoped.
        other_before["completed_albums"]["Artist - Existing"]["label"] = "Edited during fetch"
        self.assertEqual(self.load("other"), other_before)

    def test_snapshot_queries_share_one_consistent_read_transaction(self):
        before = self.load()
        load_progress = AlbumStateRepository._load_albums_in_progress

        def write_between_snapshot_queries(repository):
            with self.sessions() as writer:
                user = UserRepository(writer).require_user_by_slug("listener")
                current = AlbumStateRepository(writer, user)
                state = {
                    **before, "last_checked": self.manual_listen,
                    "completed_albums": {**before["completed_albums"],
                                         "Artist - Manual": self.record("Manual")},
                }
                current.replace(state)
            return load_progress(repository)

        with self.sessions() as reader:
            user = UserRepository(reader).require_user_by_slug("listener")
            # The first cursor query establishes the snapshot before the writer.
            with patch.object(AlbumStateRepository, "_load_albums_in_progress", write_between_snapshot_queries):
                snapshot = AlbumStateRepository(reader, user).load_for_sync()
        self.assertEqual(snapshot, before)
        self.assertEqual(self.load()["last_checked"], self.manual_listen)
        self.assertIn("Artist - Manual", self.load()["completed_albums"])

    def test_concurrent_deletion_is_not_resurrected(self):
        with self.sessions() as session:
            user = UserRepository(session).require_user_by_slug("listener")
            AlbumLibrary(session, user).add_album(self.record("Removed"), self.old_listen)

        def delete_during_fetch():
            self.on_fetch = lambda: None
            with self.sessions() as session:
                user = UserRepository(session).require_user_by_slug("listener")
                library = AlbumLibrary(session, user)
                library.remove_album(library.catalog.require_by_key("Artist - Removed").id)
                library.remove_listen(library.catalog.require_by_key("Artist - Existing").id, self.old_listen)

        self.on_fetch = delete_during_fetch
        self.run_sync()
        state = self.load()
        self.assertNotIn("Artist - Removed", state["completed_albums"])
        self.assertEqual(state["completed_albums"]["Artist - Existing"]["listen_history"],
                         [self.track_times[-1]])

    def test_overlapping_sync_reloads_cursor_and_keeps_newer_progress(self):
        self.tracks.append(self.track(0, album_id="partial", title="Partial", minutes=0))
        inner_results = []

        def overlapping_sync():
            self.on_fetch = lambda: None
            inner_results.append(self.run_sync())

        self.on_fetch = overlapping_sync
        result = self.run_sync()
        state = self.load()
        self.assertEqual(self.fetches, [None, None, self.timestamp(0)])
        self.assertEqual(inner_results[0]["completed_albums"], 1)
        self.assertEqual(result["completed_albums"], 0)
        self.assertEqual(state["last_checked"], self.timestamp(0))
        self.assertEqual(state["albums_in_progress"]["partial"]["played_tracks"], ["track-0"])
        self.assertEqual(state["completed_albums"]["Artist - Existing"]["listen_history"],
                         [self.old_listen, self.track_times[-1]])

    def test_another_profiles_sync_does_not_invalidate_snapshot(self):
        def other_sync():
            self.on_fetch = lambda: None
            self.run_sync("other")

        self.on_fetch = other_sync
        self.run_sync()
        self.assertEqual(self.fetches, [None, None])
        self.assertEqual(self.load()["last_checked"], self.load("other")["last_checked"])

    def test_simultaneous_syncs_serialize_save_and_only_complete_once(self):
        both_fetching = Barrier(2)
        counter_lock = Lock()
        calls = 0

        def concurrent_fetch():
            nonlocal calls
            with counter_lock:
                calls += 1
                first_attempt = calls <= 2
            if first_attempt:
                both_fetching.wait(timeout=5)

        self.on_fetch = concurrent_fetch
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(self.run_sync) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(result["completed_albums"] for result in results), [0, 1])
        self.assertEqual(len(self.fetches), 3)
        self.assertEqual(self.load()["completed_albums"]["Artist - Existing"]["listen_history"],
                         [self.old_listen, self.track_times[-1]])

    def test_conflict_retries_are_bounded_and_do_not_save_stale_state(self):
        def keep_writing():
            with self.sessions() as session:
                user = UserRepository(session).require_user_by_slug("listener")
                AlbumLibrary(session, user).add_album(self.record(f"Concurrent {len(self.fetches)}"), self.manual_listen)

        self.on_fetch = keep_writing
        with self.assertRaises(SpotifySyncConflict):
            self.run_sync()
        state = self.load()
        self.assertEqual(len(self.fetches), service.MAX_SYNC_ATTEMPTS)
        self.assertIsNone(state["last_checked"])
        self.assertEqual(len(state["completed_albums"]), 1 + service.MAX_SYNC_ATTEMPTS)
        self.assertEqual(state["completed_albums"]["Artist - Existing"]["listen_history"], [self.old_listen])
        self.assertIsNone(self.credentials()[0])
        self.on_fetch = lambda: None
        self.run_sync()
        self.assertEqual(self.load()["last_checked"], self.track_times[-1])

    def test_failed_state_write_rolls_back_then_can_retry(self):
        before = self.load()
        with patch.object(AlbumStateRepository, "_sync_albums_in_progress", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                self.run_sync()
        self.assertEqual(self.load(), before)
        self.assertIsNone(self.credentials()[0])
        self.run_sync()
        self.assertEqual(self.load()["completed_albums"]["Artist - Existing"]["listen_history"],
                         [self.old_listen, self.track_times[-1]])

    def test_provider_failure_does_not_write_and_success_status_failure_does_not_duplicate(self):
        before = self.load()
        with patch.object(service, "SpotifyAPI", side_effect=TimeoutError("offline")):
            with self.assertRaises(TimeoutError):
                self.run_sync()
        self.assertEqual(self.load(), before)
        self.assertIsNone(self.credentials()[0])
        with patch.object(SpotifyCredentialsRepository, "record_sync_success", side_effect=RuntimeError("status failed")):
            with self.assertRaisesRegex(RuntimeError, "status failed"):
                self.run_sync()
        self.assertEqual(self.load()["last_checked"], self.track_times[-1])
        self.run_sync()
        self.assertEqual(self.load()["completed_albums"]["Artist - Existing"]["listen_history"],
                         [self.old_listen, self.track_times[-1]])
        self.assertIsNotNone(self.credentials()[0])
