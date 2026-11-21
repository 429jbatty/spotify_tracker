import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest


class StructuredLoggingTests(unittest.TestCase):
    def run_script(self, script):
        with tempfile.TemporaryDirectory() as data_dir:
            env = dict(os.environ, DATA_DIR=data_dir, DATABASE_URL=f"sqlite:///{data_dir}/test.sqlite")
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)], env=env,
                capture_output=True, text=True, timeout=30, check=True,
            )
        return [json.loads(line) for line in result.stderr.splitlines() if line.startswith('{')]

    def test_api_access_hides_query_and_correlates_request(self):
        events = self.run_script('''
            from fastapi.testclient import TestClient
            from backend.app.main import app
            with TestClient(app) as client:
                response = client.get('/api/health?token=secret-value')
                assert response.status_code == 200
        ''')
        event = next(e for e in events if e['event'] == 'http_request_completed')
        self.assertEqual(event['status_code'], 200)
        self.assertEqual(event['route'], '/api/health')
        self.assertTrue(event['request_id'])
        self.assertNotIn('secret-value', str(events))

    def test_request_failure_is_correlated_and_sanitized(self):
        events = self.run_script("""
            from fastapi.testclient import TestClient
            from backend.app.main import app
            @app.get('/test-failure')
            async def fail():
                raise ValueError('access_token=secret-value')
            with TestClient(app, raise_server_exceptions=False) as client:
                assert client.get('/test-failure').status_code == 500
        """)
        failure = next(e for e in events if e['event'] == 'http_request_failed')
        self.assertTrue(failure['request_id'])
        self.assertIn('ValueError', failure['exception'])
        self.assertNotIn('secret-value', str(events))

    def test_sync_failure_keeps_user_context_and_restores_it(self):
        events = self.run_script("""
            import logging
            from unittest.mock import patch
            from structlog.contextvars import bind_contextvars
            from backend.app.logging_config import configure_logging
            from backend.app.services.spotify_tracking_service import run_tracking_for_user
            configure_logging()
            def fail(_slug):
                bind_contextvars(user_id=42)
                raise RuntimeError('offline')
            with patch('backend.app.services.spotify_tracking_service._run_tracking_for_user', side_effect=fail):
                try: run_tracking_for_user('test')
                except RuntimeError: pass
            logging.getLogger('test').info('outside_sync')
        """)
        failure = next(e for e in events if e['event'] == 'spotify_sync_failed')
        self.assertEqual(failure['user_id'], 42)
        self.assertTrue(failure['sync_run_id'])
        outside = next(e for e in events if e['event'] == 'outside_sync')
        self.assertNotIn('user_id', outside)
        self.assertNotIn('sync_run_id', outside)

    def test_legacy_header_and_url_redaction(self):
        events = self.run_script("""
            import logging
            from backend.app.logging_config import configure_logging
            configure_logging()
            logger = logging.getLogger('test')
            for value in ('Authorization: Basic abc123', 'Cookie: session=secretvalue; other=hiddenvalue', "{'access_token': 'dictsecret'}", "{'Cookie': 'session=cookiesecret; other=cookieother'}", 'https://login:passvalue@example.test/path?api_key=querysecret'):
                logger.warning('%s', value)
        """)
        rendered = str(events)
        for secret in ('abc123', 'secretvalue', 'hiddenvalue', 'dictsecret', 'cookiesecret', 'cookieother', 'passvalue', 'querysecret'):
            self.assertNotIn(secret, rendered)

    def test_worker_entrypoint_and_stdlib_context(self):
        events = self.run_script('''
            import logging
            from unittest.mock import patch
            from backend.app.jobs.track_all_users import main
            from structlog.contextvars import bound_contextvars
            with patch('backend.app.jobs.track_all_users.run_tracking_for_all_users', return_value={'a': {}}):
                main()
            with bound_contextvars(import_session_id=99):
                logging.getLogger('test').warning('URL https://example.test/path?token=secret-value')
        ''')
        self.assertTrue(any(e['event'] == 'spotify_sync_batch_completed' for e in events))
        warning = next(e for e in events if e.get('import_session_id') == 99)
        self.assertNotIn('secret-value', str(warning))

    def test_import_failure_logs_in_user_and_session_scope(self):
        events = self.run_script("""
            from types import SimpleNamespace
            from unittest.mock import Mock, patch
            from backend.app.logging_config import configure_logging
            from backend.app.services.import_service import run_import_session
            configure_logging()
            item = SimpleNamespace(user_id=42, user=SimpleNamespace(slug='test'), source='lastfm')
            session = Mock(); session.get.return_value = item
            summary = SimpleNamespace(progress_label='fetch', progress_current=1, progress_total=2)
            with patch('backend.app.services.import_service.SqliteStateRepository'), patch('backend.app.services.import_service._run_lastfm_import_session', side_effect=ValueError('failed')), patch('backend.app.services.import_service._session_summary', return_value=summary), patch('backend.app.services.import_service._append_import_log'), patch('backend.app.services.import_service._set_import_progress'):
                try: run_import_session(session, 99)
                except ValueError: pass
        """)
        failure = next(e for e in events if e['event'] == 'import_failed')
        self.assertEqual(failure['user_id'], 42)
        self.assertEqual(failure['import_session_id'], 99)

    def test_async_context_isolation(self):
        events = self.run_script("""
            import asyncio
            import structlog
            from structlog.contextvars import bound_contextvars
            from backend.app.logging_config import configure_logging
            configure_logging()
            async def task(user_id):
                with bound_contextvars(user_id=user_id):
                    await asyncio.sleep(0)
                    structlog.get_logger('test').info('async_event')
            async def main():
                await asyncio.gather(task(1), task(2))
            asyncio.run(main())
        """)
        self.assertEqual({e['user_id'] for e in events if e['event'] == 'async_event'}, {1, 2})

    def test_import_background_thread_binds_and_restores_context(self):
        events = self.run_script('''
            import logging
            import threading
            from contextlib import nullcontext
            from unittest.mock import patch
            from backend.app.logging_config import configure_logging
            from backend.app.routers.imports import _run_import_background_worker
            configure_logging()
            def run(session, session_id):
                logging.getLogger('test').info('thread_event')
            with patch('backend.app.routers.imports._session_factory', return_value=lambda: nullcontext(None)), patch('backend.app.routers.imports.import_service.run_import_session', side_effect=run):
                threads = [threading.Thread(target=_run_import_background_worker, args=(n,)) for n in (1, 2)]
                for t in threads: t.start()
                for t in threads: t.join()
            logging.getLogger('test').info('outside_event')
        ''')
        inside = [e for e in events if e['event'] == 'thread_event']
        self.assertEqual({e['import_session_id'] for e in inside}, {1, 2})
        self.assertNotIn('import_session_id', next(e for e in events if e['event'] == 'outside_event'))


if __name__ == '__main__':
    unittest.main()
