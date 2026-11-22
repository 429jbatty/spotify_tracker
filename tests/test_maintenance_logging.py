import unittest
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError
from structlog.testing import capture_logs

import metadata_refresh_service

from backend.app import migrations
from backend.app.persistence_logging import database_error_fields
from backend.app.request_logging import RequestLoggingMiddleware
from backend.app.services import import_service
from backend.app.services.artwork_backfill_service import ArtworkBackfillResult, ArtworkBackfillService
from backend.app.services.credit_fact_service import AlbumCreditSource, rebuild_credit_facts


class MaintenanceLoggingTests(unittest.TestCase):
    def test_migration_failure_reports_completed_stages_without_claiming_rollback(self):
        def succeeds(engine):
            pass
        def migrate_default_user(engine):
            raise RuntimeError('fixture')
        with patch.object(migrations, 'migrate_spotify_sync_eligibility', succeeds), \
             patch.object(migrations, 'migrate_default_user', migrate_default_user), \
             capture_logs() as events:
            with self.assertRaises(RuntimeError):
                migrations.run_sqlite_migrations(Mock())
        self.assertEqual(events[0]['event'], 'database_migrations_failed')
        self.assertEqual(events[0]['stage'], 'migrate_default_user')
        self.assertEqual(events[0]['stages_completed'], 1)
        self.assertNotIn('rolled_back', events[0])

    def test_database_error_fields_never_include_statement_or_values(self):
        exc = IntegrityError('INSERT INTO secret (password) VALUES (?)', ('private-token',), Exception('error'))
        fields = database_error_fields(exc)
        self.assertEqual(fields, {'database_error_type': 'IntegrityError', 'database_operation': 'write'})
        self.assertNotIn('private-token', repr(fields))
        self.assertEqual(database_error_fields(ValueError('ordinary failure')), {})

    def test_database_errors_distinguish_lock_and_disk_full_without_messages(self):
        for raw, expected in [('database is locked', 'locked'), ('database or disk is full', 'disk_full')]:
            try:
                raise OperationalError('UPDATE sensitive SET value=?', ('private-token',), sqlite3.OperationalError(raw))
            except OperationalError as exc:
                fields = database_error_fields(exc)
            self.assertEqual(fields['database_reason'], expected)
            self.assertIn('test_maintenance_logging.py:', fields['database_location'])
            self.assertNotIn('private-token', repr(fields))
            self.assertNotIn('sensitive', repr(fields))

    def test_request_write_failure_is_queryable_without_sql_or_parameters(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        @app.post('/fixture')
        def fail():
            raise IntegrityError('INSERT INTO secret (password) VALUES (?)', ('private-token',), Exception('error'))
        with capture_logs() as events:
            response = TestClient(app, raise_server_exceptions=False).post('/fixture')
        self.assertEqual(response.status_code, 500)
        failure = next(event for event in events if event['event'] == 'http_request_failed')
        self.assertEqual(failure['database_operation'], 'write')
        self.assertEqual(failure['database_error_type'], 'IntegrityError')
        self.assertNotIn('private-token', repr(failure))
        self.assertNotIn('INSERT', repr(failure))
        self.assertNotIn('exc_info', failure)

    def test_batch_refresh_database_failure_excludes_statement_and_parameters(self):
        exc = IntegrityError('INSERT INTO secrets VALUES (?)', ('private-token',), sqlite3.IntegrityError('constraint failed'))
        with capture_logs() as events:
            metadata_refresh_service._log_refresh_error('Fixture - Album', exc)
        self.assertEqual(events[0]['database_operation'], 'write')
        self.assertFalse(events[0]['exc_info'])
        self.assertNotIn('private-token', repr(events))
        self.assertNotIn('INSERT INTO', repr(events))

    def test_post_import_backfill_never_logs_or_persists_sql_parameters(self):
        repository = Mock()
        repository.album_ids_for_import_session_artwork_backfill.side_effect = IntegrityError(
            'INSERT INTO secrets VALUES (?)', ('private-token',), sqlite3.IntegrityError('constraint failed'),
        )
        session = Mock()
        import_session = SimpleNamespace(status='completed', id=7)
        with patch.object(import_service, '_append_import_log') as append_log, capture_logs() as events:
            import_service._run_post_import_artwork_backfill(session, repository, import_session)
        event = next(e for e in events if e['event'] == 'post_import_artwork_backfill_failed')
        self.assertEqual(event['database_operation'], 'write')
        self.assertNotIn('private-token', repr(events))
        self.assertNotIn('INSERT INTO', repr(events))
        self.assertNotIn('private-token', repr(append_log.call_args))
        self.assertNotIn('INSERT INTO', repr(append_log.call_args))
        self.assertEqual(import_session.status, 'completed')

    def test_backfill_reports_completed_items_on_failure(self):
        repository = Mock()
        repository.albums_for_artwork_backfill.return_value = [{'id': 1}, {'id': 2}]
        service = ArtworkBackfillService(media_dir='/unused')
        first = ArtworkBackfillResult(album_id=1, album_key='Fixture', status='updated')
        with patch.object(service, '_backfill_album', side_effect=[first, RuntimeError('failed')]), capture_logs() as events:
            with self.assertRaises(RuntimeError):
                service.backfill_missing_artwork(repository, apply=True)
        event = events[0]
        self.assertEqual((event['event'], event['processed'], event['updated'], event['total']), ('artwork_backfill_failed', 1, 1, 2))
        self.assertTrue(event['partial_commits_possible'])

    def test_credit_rebuild_reports_only_committed_results(self):
        source = AlbumCreditSource(album_id=4, artist='A', artist_mbid=None, metadata_json={})
        session = Mock()
        session.execute.return_value = SimpleNamespace(rowcount=2)
        with patch('backend.app.services.credit_fact_service.load_album_credit_sources', return_value=[source]), \
             patch('backend.app.services.credit_fact_service._facts_for_album', return_value=[]), capture_logs() as events:
            rebuild_credit_facts(session, commit=False)
            self.assertEqual(events, [])
            rebuild_credit_facts(session, commit=True)
            self.assertEqual((events[0]['event'], events[0]['albums'], events[0]['deleted']), ('credit_facts_rebuilt', 1, 2))
            session.commit.side_effect = RuntimeError('failed')
            with self.assertRaises(RuntimeError):
                rebuild_credit_facts(session, commit=True)
        self.assertEqual(events[-1]['event'], 'credit_facts_rebuild_failed')
        self.assertEqual(events[-1]['stage'], 'commit')


if __name__ == '__main__':
    unittest.main()
