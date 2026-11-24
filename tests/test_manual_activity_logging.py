import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker
from structlog.contextvars import get_contextvars

from tests.database_helpers import create_schema
from backend.app.main import create_app
from backend.app.database.models import Album, AlbumListen, UserAlbum
from backend.app.database.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.services import auth_service, manual_album_service
from backend.app.schemas import ManualAlbumCreate


class ManualActivityLoggingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_url = f"sqlite:///{Path(self.directory.name) / 'activity.sqlite'}"
        self.engine = create_schema(self.database_url)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        with self.sessions() as session:
            repository = SqliteStateRepository(session)
            account = auth_service.create_account(session, email="owner@example.com", password="unused")
            repository.user.owner_account_id = account.id
            self.user_id = repository.user.id
            token = auth_service.create_session(session, account=account)
            session.commit()
        environment = patch.dict("os.environ", {"DATABASE_URL": self.database_url, "MEDIA_DIR": self.directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(create_app())
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        self.events = []

        class Logger:
            def info(inner, event, **fields):
                self.events.append({"event": event, **fields, **get_contextvars()})

        logger_patch = patch("backend.app.services.user_activity_logging.structlog.get_logger", return_value=Logger())
        logger_patch.start()
        self.addCleanup(logger_patch.stop)

    def create_album(self, path="/api/users/jacob/albums", **values):
        with patch("backend.app.services.manual_album_service.album_metadata_service.get_album_metadata", return_value={}):
            return self.client.post(path, json={"artist": "Artist", "name": "Record", **values})

    def test_manual_creation_listen_dedupe_deletion_and_request_context(self):
        response = self.create_album(listen_date="2026-01-01T00:00:00Z")
        self.assertEqual(response.status_code, 201)
        album_id = response.json()["id"]
        self.assertEqual([e["event"] for e in self.events], ["album_manually_added", "album_listen_added"])
        for event in self.events:
            self.assertEqual((event["user_id"], event["profile_slug"], event["album_id"]), (self.user_id, "jacob", album_id))
            self.assertEqual((event["album_artist"], event["album_title"], event["action_source"]), ("Artist", "Record", "manual"))
            self.assertTrue(event.get("request_id"))
        self.events.clear()
        path = f"/api/users/jacob/albums/{album_id}/listens"
        self.assertEqual(self.client.post(path, json={"listened_at": "2026-01-01T00:00:00Z"}).status_code, 200)
        self.assertEqual(self.events, [])
        self.assertEqual(self.client.post(path, json={"listened_at": "2026-01-02T00:00:00Z"}).status_code, 200)
        self.assertEqual(self.client.request("DELETE", path, json={"listened_at": "2026-01-02T00:00:00Z"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/users/jacob/albums/{album_id}").status_code, 204)
        self.assertEqual([e["event"] for e in self.events], ["album_listen_added", "album_listen_removed", "album_removed"])
        self.assertEqual(self.events[-1]["album_title"], "Record")
        with self.sessions() as session:
            self.assertIsNone(session.get(Album, album_id))

    def test_reusing_membership_logs_only_the_new_listen(self):
        created = self.create_album(listen_date="2026-01-01T00:00:00Z")
        self.assertEqual(created.status_code, 201)
        self.events.clear()
        repeated = self.create_album(listen_date="2026-01-02T00:00:00Z")
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(repeated.json()["id"], created.json()["id"])
        self.assertEqual([e["event"] for e in self.events], ["album_listen_added"])
        self.events.clear()
        self.assertEqual(self.create_album(listen_date="2026-01-02T00:00:00Z").status_code, 201)
        self.assertEqual(self.events, [])

    def test_metadata_lookup_does_not_hold_sqlite_writer_lock(self):
        import sqlite3
        database_path = Path(self.directory.name) / "activity.sqlite"
        lock_acquired = []
        def lookup(*args, **kwargs):
            with sqlite3.connect(database_path, timeout=0.1) as connection:
                connection.execute("BEGIN IMMEDIATE")
                lock_acquired.append(True)
                connection.rollback()
            return {}
        with patch("backend.app.services.manual_album_service.album_metadata_service.get_album_metadata", side_effect=lookup):
            response = self.client.post("/api/users/jacob/albums", json={"artist": "Artist", "name": "Record"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(lock_acquired, [True])
        self.assertEqual([e["event"] for e in self.events], ["album_manually_added"])

    def test_compatibility_routes_and_unauthorized_requests(self):
        self.assertEqual(self.create_album(path="/api/albums").status_code, 201)
        self.assertEqual([e["event"] for e in self.events], ["album_manually_added"])
        self.events.clear()
        unauthorized = self.client.post("/api/users/jacob/albums", json={"artist": "Other", "name": "Other"}, headers={"Authorization": ""})
        self.assertIn(unauthorized.status_code, (401, 403))
        self.assertEqual(self.events, [])

    def test_shared_album_and_implicit_membership_are_user_scoped(self):
        with self.sessions() as session:
            other = UserRepository(session).create_user(slug="other", display_name="Other")
            other_id = other.id
            repo = SqliteStateRepository(session, user_slug="other")
            album_id = repo.create_completed_album({"artist": "Shared", "name": "Album", "source": "spotify_sync"})["id"]
        with self.sessions() as session:
            repo = SqliteStateRepository(session, user_slug="jacob")
            manual_album_service.add_manual_album_listen(repo, album_id, "2026-01-01T00:00:00Z")
        self.assertEqual([e["event"] for e in self.events], ["album_manually_added", "album_listen_added"])
        self.assertTrue(all(e["user_id"] == self.user_id and e["action_source"] == "manual" for e in self.events))
        self.events.clear()
        with self.sessions() as session:
            repo = SqliteStateRepository(session, user_slug="jacob")
            manual_album_service.delete_manual_album(repo, album_id)
        with self.sessions() as session:
            self.assertIsNotNone(session.get(Album, album_id))
            self.assertIsNotNone(session.scalar(select(UserAlbum).where(UserAlbum.user_id == other_id, UserAlbum.album_id == album_id)))
        self.assertEqual([e["event"] for e in self.events], ["album_removed"])

    def test_failed_commit_emits_nothing_and_logging_failure_does_not_fail_write(self):
        with self.sessions() as session:
            repo = SqliteStateRepository(session, user_slug="jacob")
            with patch("backend.app.services.manual_album_service._metadata_record", return_value=None), patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
                with self.assertRaises(RuntimeError):
                    manual_album_service.create_manual_album(repo, ManualAlbumCreate(artist="X", name="Y"))
            session.rollback()
        self.assertEqual(self.events, [])
        with patch("backend.app.services.user_activity_logging.structlog.get_logger", side_effect=RuntimeError("logging failed")):
            response = self.create_album()
        self.assertEqual(response.status_code, 201)
        with self.sessions() as session:
            self.assertIsNotNone(session.get(Album, response.json()["id"]))

    def test_feedback_events_follow_replacement_semantics_without_note_text(self):
        album_id = self.create_album().json()["id"]
        self.events.clear()
        path = f"/api/users/jacob/albums/{album_id}/your-feedback"
        self.assertEqual(self.client.put(path, json={"rating": 7, "notes": " private note "}).status_code, 200)
        self.assertEqual([e["event"] for e in self.events], ["album_rating_changed", "album_note_changed"])
        self.assertEqual([(e["change"], e.get("rating")) for e in self.events], [("added", 7), ("added", None)])
        self.assertNotIn("private note", repr(self.events))
        self.events.clear()
        self.assertEqual(self.client.put(path, json={"rating": 7, "notes": "private note"}).status_code, 200)
        self.assertEqual(self.events, [])
        self.assertEqual(self.client.put(path, json={"rating": 8, "notes": "different"}).status_code, 200)
        self.assertEqual([e["change"] for e in self.events], ["updated", "updated"])
        self.events.clear()
        self.assertEqual(self.client.put(f"/api/albums/{album_id}/your-feedback", json={}).status_code, 200)
        self.assertEqual([e["event"] for e in self.events], ["album_rating_removed", "album_note_removed"])
        self.events.clear()
        self.assertEqual(self.client.put(path, json={"rating": 11}).status_code, 422)
        self.assertEqual(self.events, [])

    def test_tag_events_report_normalized_changes_and_ignore_reordering(self):
        album_id = self.create_album().json()["id"]
        self.events.clear()
        path = f"/api/users/jacob/albums/{album_id}/your-tags"
        self.assertEqual(self.client.put(path, json={"your_tags": [" raw ", "lush", "raw"]}).status_code, 200)
        self.assertEqual(len(self.events), 1)
        self.assertEqual((self.events[0]["added_tags"], self.events[0]["removed_tags"]), (["lush", "raw"], []))
        self.events.clear()
        self.assertEqual(self.client.put(path, json={"your_tags": ["lush", "raw"]}).status_code, 200)
        self.assertEqual(self.events, [])
        self.assertEqual(self.client.put(f"/api/albums/{album_id}/your-tags", json={"your_tags": ["lush", "noisy"]}).status_code, 200)
        self.assertEqual((self.events[0]["added_tags"], self.events[0]["removed_tags"]), (["noisy"], ["raw"]))
        self.events.clear()
        self.assertEqual(self.client.put(path, json={"your_tags": ["invalid"]}).status_code, 422)
        self.assertEqual(self.events, [])

    def test_feedback_and_tag_failures_do_not_emit_or_commit(self):
        album_id = self.create_album().json()["id"]
        self.events.clear()
        for update in (
            lambda repo: manual_album_service.update_manual_album_feedback(repo, album_id, rating=8, notes="secret"),
            lambda repo: manual_album_service.update_manual_album_tags(repo, album_id, ["lush"]),
        ):
            with self.sessions() as session:
                repository = SqliteStateRepository(session)
                with patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
                    with self.assertRaises(RuntimeError):
                        update(repository)
                session.rollback()
            self.assertEqual(self.events, [])
        with self.sessions() as session:
            membership = session.scalar(select(UserAlbum).where(UserAlbum.user_id == self.user_id, UserAlbum.album_id == album_id))
            self.assertIsNone(membership.rating)
            self.assertIsNone(membership.notes)
            self.assertEqual(membership.your_tags, [])

    def test_concurrent_identical_feedback_and_tags_emit_once(self):
        album_id = self.create_album().json()["id"]
        self.events.clear()
        for update in (
            lambda repo: manual_album_service.update_manual_album_feedback(repo, album_id, rating=8, notes=None),
            lambda repo: manual_album_service.update_manual_album_tags(repo, album_id, ["lush"]),
        ):
            ready = threading.Barrier(2)
            def run():
                with self.sessions() as session:
                    repo = SqliteStateRepository(session)
                    ready.wait(timeout=5)
                    update(repo)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run) for _ in range(2)]
                for future in futures:
                    future.result(timeout=15)
        self.assertEqual([e["event"] for e in self.events], ["album_rating_changed", "album_tags_changed"])

    def test_import_feedback_does_not_emit_manual_activity(self):
        with self.sessions() as session:
            repository = SqliteStateRepository(session)
            album_id = repository.create_completed_album({"artist": "Import", "name": "Album"})["id"]
            repository.update_user_album_feedback(album_id, rating=8, notes="imported")
            repository.update_user_album_tags(album_id, ["lush"])
        self.assertEqual(self.events, [])

    def test_import_listen_does_not_repeat_membership_lookup_for_change_facts(self):
        with self.sessions() as session:
            repository = SqliteStateRepository(session)
            album_id = repository.create_completed_album({"artist": "Artist", "name": "Import"})["id"]

        statements = []
        def collect_membership_queries(connection, cursor, statement, parameters, context, executemany):
            if "FROM user_albums" in statement:
                statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", collect_membership_queries)
        try:
            with self.sessions() as session:
                repository = SqliteStateRepository(session)
                repository.add_album_listen(album_id, "2026-01-01T00:00:00Z")
        finally:
            event.remove(self.engine, "before_cursor_execute", collect_membership_queries)
        # One lookup ensures membership; the other builds the returned album record.
        self.assertEqual(len(statements), 2)
        self.assertEqual(self.events, [])

    def test_concurrent_duplicate_listens_emit_once(self):
        with self.sessions() as session:
            repo = SqliteStateRepository(session, user_slug="jacob")
            album_id = repo.create_completed_album({"artist": "Artist", "name": "Concurrent"})["id"]
        ready = threading.Barrier(2)
        def add_listen():
            with self.sessions() as session:
                repo = SqliteStateRepository(session, user_slug="jacob")
                ready.wait(timeout=5)
                manual_album_service.add_manual_album_listen(repo, album_id, "2026-01-01T00:00:00Z")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(add_listen) for _ in range(2)]
            for future in futures:
                future.result(timeout=15)
        self.assertEqual([event["event"] for event in self.events], ["album_listen_added"])
        with self.sessions() as session:
            self.assertEqual(len(session.scalars(select(AlbumListen).where(AlbumListen.album_id == album_id)).all()), 1)


if __name__ == "__main__":
    unittest.main()
