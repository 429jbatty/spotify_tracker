import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from fastapi import HTTPException

import httpx
import musicbrainzngs
import musicbrainz_client
from spotipy.exceptions import SpotifyException

from structlog.testing import capture_logs
from structlog.contextvars import bound_contextvars, get_contextvars
import album_metadata_service

from backend.app.schemas import ManualAlbumCreate
from backend.app.services import auth_service, lastfm_import_client, manual_album_service, metadata_refresh_logging, spotify_tracking_service
from backend.app.routers import auth, spotify
from backend.app.services.artwork_cache_service import ArtworkCacheService


class DiagnosticLoggingTests(unittest.TestCase):
    def test_concurrent_manual_lookups_keep_request_context_and_album_identity(self):
        barrier = threading.Barrier(2)
        observed = []
        class Capture:
            def info(self, event, **fields):
                observed.append((event, fields, get_contextvars()))
        def no_candidate(*args, **kwargs):
            barrier.wait(timeout=5)
            return None
        def lookup(request_id, artist):
            with bound_contextvars(request_id=request_id):
                manual_album_service._metadata_record(ManualAlbumCreate(artist=artist, name='Fixture Album'))
        with patch.object(album_metadata_service, 'resolve_spotify_candidate', return_value=None), \
             patch.object(album_metadata_service, 'resolve_musicbrainz_candidate', side_effect=no_candidate), \
             patch.object(album_metadata_service, 'metadata_logger', Capture()):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(lookup, 'request-a', 'Artist A'), pool.submit(lookup, 'request-b', 'Artist B')]
                for future in futures:
                    future.result(timeout=10)
        self.assertEqual({(fields['album_artist'], context['request_id']) for _, fields, context in observed}, {('Artist A', 'request-a'), ('Artist B', 'request-b')})
        self.assertTrue(all(fields['album_title'] == 'Fixture Album' for _, fields, _ in observed))

    def test_manual_metadata_reports_no_match_without_user_input(self):
        with patch.object(manual_album_service, '_metadata_slots') as slots, \
             patch.object(manual_album_service.album_metadata_service, 'get_album_metadata', return_value={}), \
             capture_logs() as events:
            slots.acquire.return_value = True
            self.assertIsNone(manual_album_service._metadata_record(ManualAlbumCreate(artist='Private Artist', name='Private Album')))
        event = next(e for e in events if e['event'] == 'manual_metadata_fallback')
        self.assertEqual(event['reason'], 'no_match')
        self.assertNotIn('Private', repr(event))

    def test_refresh_reports_committed_success_and_classified_failure(self):
        repository = Mock()
        repository.get_completed_album_record_by_id.return_value = {'artist': 'A', 'name': 'B'}
        repository.replace_completed_album_metadata_by_id_or_merge_duplicate.return_value = {'id': 4}
        with patch.object(metadata_refresh_logging.metadata_refresh_service, 'refresh_album_record', return_value={'_refresh_warnings': ['warning']}), capture_logs() as events:
            self.assertEqual(metadata_refresh_logging.refresh_album(repository, 4), {'id': 4})
        self.assertEqual([(e['event'], e['warning_count']) for e in events], [('album_metadata_refreshed', 1)])
        repository.replace_completed_album_metadata_by_id_or_merge_duplicate.side_effect = RuntimeError('secret URL')
        with patch.object(metadata_refresh_logging.metadata_refresh_service, 'refresh_album_record', return_value={}), capture_logs() as events:
            with self.assertRaises(RuntimeError):
                metadata_refresh_logging.refresh_album(repository, 4)
        self.assertEqual(events[0]['event'], 'album_metadata_refresh_failed')
        self.assertNotIn('secret', repr(events))

    def test_artwork_download_failure_logs_stage_without_url(self):
        with tempfile.TemporaryDirectory() as directory, capture_logs() as events:
            def fail(url):
                raise OSError('https://example.test/?secret=123')
            result = ArtworkCacheService(directory, downloader=fail).cache_album_artwork({'id': 4, 'album_key': 'A - B', 'image_url': 'https://example.test/cover'})
        self.assertFalse(result.cached)
        self.assertEqual((events[0]['event'], events[0]['stage']), ('artwork_cache_failed', 'download'))
        self.assertNotIn('secret', repr(events))


    def test_lastfm_timeout_logged_once_after_retries_without_credentials(self):
        client = Mock()
        client.get.side_effect = httpx.ReadTimeout('secret-value')
        with patch.object(lastfm_import_client.time, 'sleep'), capture_logs() as events:
            with self.assertRaises(ValueError):
                lastfm_import_client._fetch_lastfm_page(client=client, username='private-user', api_key='secret-value', page=3, from_timestamp=None)
        self.assertEqual(client.get.call_count, lastfm_import_client.LASTFM_FETCH_RETRIES)
        self.assertEqual([(e['event'], e['reason'], e['attempts']) for e in events], [('lastfm_request_failed', 'timeout', 3)])
        self.assertNotIn('secret-value', repr(events))
        self.assertNotIn('private-user', repr(events))

    def test_auth_failure_logs_category_without_callback_credentials(self):
        session = Mock()
        session_context = Mock()
        session_context.__enter__ = Mock(return_value=session)
        session_context.__exit__ = Mock(return_value=False)
        with patch.object(auth, '_session_factory', return_value=lambda: session_context), \
             patch.object(auth, 'get_settings', return_value=SimpleNamespace(frontend_origin='https://frontend.test')), \
             patch.object(auth.auth_service, 'complete_google_sign_in', side_effect=HTTPException(status_code=503, detail='private')), \
             capture_logs() as events:
            response = auth.google_callback(code='secret-code', state='secret-state', error=None)
        self.assertEqual(response.status_code, 303)
        self.assertEqual((events[0]['event'], events[0]['reason']), ('sign_in_failed', 'unavailable'))
        self.assertNotIn('secret', repr(events))
        with capture_logs() as events:
            with self.assertRaises(HTTPException):
                spotify.spotify_callback(code='secret-code', state=None)
        self.assertEqual(events[0]['reason'], 'invalid_request')
        self.assertNotIn('secret', repr(events))

    def test_google_success_logs_account_only_after_commit(self):
        session = Mock()
        session_context = Mock()
        session_context.__enter__ = Mock(return_value=session)
        session_context.__exit__ = Mock(return_value=False)
        account = SimpleNamespace(id=42, email='private@example.test')
        with patch.object(auth, '_session_factory', return_value=lambda: session_context), \
             patch.object(auth, 'get_settings', return_value=SimpleNamespace(frontend_origin='https://frontend.test')), \
             patch.object(auth.auth_service, 'complete_google_sign_in', return_value=(account, 'secret-token')), \
             capture_logs() as events:
            response = auth.google_callback(code='secret-code', state='secret-state', error=None)
        self.assertEqual(response.status_code, 303)
        session.commit.assert_called_once()
        self.assertEqual((events[0]['event'], events[0]['account_id']), ('sign_in_succeeded', 42))
        self.assertNotIn('secret', repr(events))
        self.assertNotIn(account.email, repr(events))

    def test_profile_denial_logs_resolved_ids_without_token(self):
        session = Mock()
        session.scalars.return_value.first.return_value = SimpleNamespace(id=10, owner_account_id=1)
        with patch.object(auth_service, 'require_account', return_value=SimpleNamespace(id=2)), capture_logs() as events:
            with self.assertRaises(HTTPException):
                auth_service.require_profile_owner(session, user_slug='private-slug', authorization='Bearer secret')
        self.assertEqual((events[0]['event'], events[0]['user_id'], events[0]['actor_account_id']), ('profile_access_denied', 10, 2))
        self.assertNotIn('secret', repr(events))
        self.assertNotIn('private-slug', repr(events))

    def test_spotify_sync_failure_classifies_rate_limit_on_existing_event(self):
        with patch.object(spotify_tracking_service, '_run_tracking_for_user', side_effect=SpotifyException(429, -1, 'rate limit')), capture_logs() as events:
            with self.assertRaises(SpotifyException):
                spotify_tracking_service.run_tracking_for_user('fixture')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]['event'], events[0]['failure_category'], events[0]['status_code']), ('spotify_sync_failed', 'rate_limited', 429))

    def test_musicbrainz_exhausted_retries_emit_once(self):
        operation = Mock(side_effect=musicbrainzngs.NetworkError('secret'))
        with patch.object(musicbrainz_client, '_rate_limited_request'), patch.object(musicbrainz_client.time, 'sleep'), capture_logs() as events:
            with self.assertRaises(musicbrainzngs.NetworkError):
                musicbrainz_client._with_retries(operation)
        self.assertEqual(operation.call_count, musicbrainz_client.MAX_RETRIES)
        self.assertEqual([e['event'] for e in events], ['musicbrainz_request_failed'])
        self.assertNotIn('secret', repr(events))

    def test_musicbrainz_spotify_lookup_logs_one_fallback_without_url(self):
        with patch.object(musicbrainz_client.musicbrainzngs, 'search_releases', side_effect=musicbrainzngs.NetworkError('secret')), \
             patch.object(musicbrainz_client.time, 'sleep'), capture_logs() as events:
            self.assertIsNone(musicbrainz_client.search_release_by_spotify_url('https://example.test/?secret=123'))
        self.assertEqual([e['event'] for e in events], ['musicbrainz_lookup_fallback'])
        self.assertNotIn('secret', repr(events))


if __name__ == '__main__':
    unittest.main()
