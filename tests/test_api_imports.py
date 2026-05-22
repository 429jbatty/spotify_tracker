import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema, get_engine
from backend.app.models import ImportedListeningEvent
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services import import_service


def sample_album_state():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {
            "Existing Artist - Existing Album": {
                "artist": "Existing Artist",
                "name": "Existing Album",
                "source": "musicbrainz",
                "listen_history": ["2026-04-01T10:00:00.000Z"],
            }
        },
        "most_recently_listened": ["Existing Artist - Existing Album"],
    }


def sample_album_state_with_tracklist():
    state = sample_album_state()
    state["completed_albums"]["Existing Artist - Existing Album"]["tracklist"] = [
        {"title": "Track 1"},
        {"title": "Track 2"},
        {"title": "Track 3"},
        {"title": "Track 4"},
    ]
    return state


class ApiImportTests(unittest.TestCase):
    def _client(self, temp_dir, state=None):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with session_factory() as session:
            repository = SqliteStateRepository(session)
            repository.save_album_state(state or sample_album_state())

        env = {
            "DATABASE_URL": database_url,
            "MEDIA_DIR": temp_dir,
            "LASTFM_API_KEY": "test-lastfm-key",
        }
        patcher = patch.dict("os.environ", env)
        patcher.start()
        self.addCleanup(patcher.stop)
        from backend.app.main import create_app

        return TestClient(create_app()), database_url

    def _mock_lastfm_client(self, payload):
        mock_response = Mock()
        mock_response.json.return_value = payload
        mock_response.raise_for_status.return_value = None

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.return_value = mock_response
        return mock_client

    def _mock_lastfm_paged_client(self, pages, total):
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        def get(_url, params):
            page = int(params["page"])
            mock_response = Mock()
            mock_response.json.return_value = {
                "recenttracks": {
                    "@attr": {
                        "page": str(page),
                        "totalPages": str(len(pages)),
                        "total": str(total),
                    },
                    "track": pages[page - 1],
                }
            }
            mock_response.raise_for_status.return_value = None
            return mock_response

        mock_client.get.side_effect = get
        return mock_client

    def _run_import_session(self, database_url, import_session_id):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            import_service.run_import_session(session, import_session_id)

    def _imported_event_count(self, database_url, match_status=None):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            query = session.query(ImportedListeningEvent)
            if match_status:
                query = query.filter(ImportedListeningEvent.match_status == match_status)
            return query.count()

    def test_preview_rejects_non_lastfm_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            response = client.post(
                "/api/users/jacob/imports/preview",
                json={"source": "csv"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Only Last.fm imports are enabled", response.json()["detail"])

    def test_lastfm_commit_returns_queued_session_before_fetching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            with patch("backend.app.routers.imports._start_import_background_worker") as start_worker:
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        self.assertIsNotNone(response.json()["import_session_id"])
        start_worker.assert_called_once_with(response.json()["import_session_id"])
        self.assertEqual(history_response.json()[0]["status"], "queued")

    def test_lastfm_background_import_persists_three_thousand_scrobbles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            scrobbles = [
                {
                    "artist": {"#text": "Existing Artist"},
                    "album": {"#text": "Existing Album"},
                    "name": f"Track {(index % 4) + 1}",
                    "date": {"uts": str(1770000000 + index * 60)},
                }
                for index in range(3000)
            ]
            pages = [scrobbles[index : index + 200] for index in range(0, len(scrobbles), 200)]
            mock_client = self._mock_lastfm_paged_client(pages, total=3000)

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")
            imported_event_count = self._imported_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(imported_event_count, 3000)
        self.assertEqual(mock_client.get.call_count, 15)
        self.assertEqual(history_response.json()[0]["status"], "completed")
        self.assertEqual(history_response.json()[0]["summary"]["new_event_rows"], 3000)
        self.assertGreaterEqual(
            history_response.json()[0]["summary"]["derived_album_listens"],
            1,
        )

    def test_lastfm_commit_creates_import_session_and_deduplicates_reimport(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1", "total": "4"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770000100"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770000200"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 4",
                            "date": {"uts": "1770000300"},
                        },
                    ],
                }
            }
            request_body = {
                "source": "lastfm",
                "lastfm_username": "jacobfm",
                "session_name": "Seed import",
            }
            mock_client = self._mock_lastfm_client(lastfm_payload)

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                first_response = client.post("/api/users/jacob/imports/commit", json=request_body)
                self._run_import_session(database_url, first_response.json()["import_session_id"])
            with patch("backend.app.services.lastfm_import_client.httpx.Client", return_value=mock_client):
                second_preview = client.post("/api/users/jacob/imports/preview", json=request_body)
            history_response = client.get("/api/users/jacob/imports")
            state_response = client.get("/api/album-state")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_preview.status_code, 200)
        self.assertEqual(second_preview.json()["summary"]["duplicate_rows"], 4)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(len(history_response.json()), 1)

        state = state_response.json()["completed_albums"]
        self.assertEqual(
            state["Existing Artist - Existing Album"]["listen_history"],
            ["2026-02-02T02:45:00+00:00", "2026-04-01T10:00:00.000Z"],
        )
        self.assertEqual(
            state["Existing Artist - Existing Album"]["entry_source"],
            "spotify_sync",
        )

    def test_delete_import_removes_session_events_and_imported_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            request_body = {
                "source": "lastfm",
                "lastfm_username": "jacobfm",
                "session_name": "Delete me",
            }
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770000100"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770000200"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 4",
                            "date": {"uts": "1770000300"},
                        },
                    ],
                }
            }
            mock_client = self._mock_lastfm_client(lastfm_payload)

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                commit_response = client.post("/api/users/jacob/imports/commit", json=request_body)
                self._run_import_session(database_url, commit_response.json()["import_session_id"])
            import_session_id = commit_response.json()["import_session_id"]
            delete_response = client.delete(f"/api/users/jacob/imports/{import_session_id}")
            history_response = client.get("/api/users/jacob/imports")
            review_response = client.get("/api/users/jacob/imports/review")
            state_response = client.get("/api/album-state")

        self.assertEqual(commit_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["deleted_events"], 4)
        self.assertEqual(delete_response.json()["deleted_listens"], 1)
        self.assertEqual(history_response.json(), [])
        self.assertEqual(review_response.json(), [])

        state = state_response.json()["completed_albums"]
        self.assertEqual(
            state["Existing Artist - Existing Album"]["listen_history"],
            ["2026-04-01T10:00:00.000Z"],
        )

    def test_lastfm_uncached_sessions_enter_pending_metadata_before_remote_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Unknown Artist"},
                            "album": {"#text": "Unknown Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Unknown Artist"},
                            "album": {"#text": "Unknown Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770000100"},
                        },
                    ],
                }
            }
            mock_client = self._mock_lastfm_client(lastfm_payload)

            def return_no_metadata(_artist, _album):
                self.assertEqual(
                    self._imported_event_count(database_url, "pending_metadata"),
                    2,
                )
                return None

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=return_no_metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            review_response = client.get("/api/users/jacob/imports/review")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(len(review_response.json()), 1)

    def test_lastfm_preview_keeps_single_scrobble_out_of_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        }
                    ],
                }
            }

            mock_response = Mock()
            mock_response.json.return_value = lastfm_payload
            mock_response.raise_for_status.return_value = None

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            with patch("backend.app.services.lastfm_import_client.httpx.Client", return_value=mock_client):
                response = client.post(
                    "/api/users/jacob/imports/preview",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_user_id"], "jacobfm")
        self.assertEqual(payload["summary"]["matched_existing_rows"], 0)
        self.assertEqual(payload["summary"]["review_candidates"], 0)

    def test_lastfm_preview_limits_pages_and_skips_metadata_matching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "100"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        }
                    ],
                }
            }

            mock_response = Mock()
            mock_response.json.return_value = lastfm_payload
            mock_response.raise_for_status.return_value = None

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            with patch("backend.app.services.lastfm_import_client.httpx.Client", return_value=mock_client), patch(
                "backend.app.services.import_service._lastfm_album_metadata",
                side_effect=AssertionError("Preview should not call metadata matching."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/preview",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.get.call_count, 5)
        self.assertEqual(response.json()["summary"]["total_rows"], 20000)

    def test_lastfm_commit_reports_upstream_failure_without_raw_500(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)

            request = httpx.Request("GET", "https://ws.audioscrobbler.com/2.0/")
            upstream_response = httpx.Response(500, request=request)
            upstream_error = httpx.HTTPStatusError(
                "Last.fm failed",
                request=request,
                response=upstream_response,
            )

            mock_response = Mock()
            mock_response.raise_for_status.side_effect = upstream_error

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.lastfm_import_client.time.sleep",
                return_value=None,
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                with self.assertRaises(ValueError):
                    self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(history_response.json()[0]["status"], "failed")
        self.assertEqual(mock_client.get.call_count, 3)

    def test_lastfm_commit_uses_musicbrainz_metadata_for_uncached_album_matching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)

            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770000100"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770000200"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 4",
                            "date": {"uts": "1770000300"},
                        },
                    ],
                }
            }

            mock_response = Mock()
            mock_response.json.return_value = lastfm_payload
            mock_response.raise_for_status.return_value = None

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            metadata = {
                "artist": "Existing Artist",
                "name": "Existing Album",
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                    {"title": "Track 4"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                review_response = client.get("/api/users/jacob/imports/review")
                history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 1)
        self.assertEqual(history_response.json()[0]["summary"]["pending_metadata_candidates"], 0)
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json(), [])

    def test_lastfm_commit_reuses_existing_album_tracklist_without_musicbrainz_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())

            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770000100"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770000200"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 4",
                            "date": {"uts": "1770000300"},
                        },
                    ],
                }
            }

            mock_response = Mock()
            mock_response.json.return_value = lastfm_payload
            mock_response.raise_for_status.return_value = None

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 1)

    def test_lastfm_commit_adds_multiple_listens_for_same_new_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)

            tracks = [
                {
                    "artist": {"#text": "New Artist"},
                    "album": {"#text": "New Album"},
                    "name": f"Track {track_number}",
                    "date": {"uts": str(timestamp)},
                }
                for timestamp, track_number in [
                    (1770000000, 1),
                    (1770000100, 2),
                    (1770000200, 3),
                    (1770000300, 4),
                    (1770200000, 1),
                    (1770200100, 2),
                    (1770200200, 3),
                    (1770200300, 4),
                ]
            ]
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": tracks,
                }
            }

            metadata = {
                "artist": "New Artist",
                "name": "New Album",
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                    {"title": "Track 4"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                state_response = client.get("/api/users/jacob/album-state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "completed")
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 2)
        imported_album = state_response.json()["completed_albums"]["New Artist - New Album"]
        self.assertEqual(len(imported_album["listen_history"]), 2)

    def test_lastfm_commit_requires_album_completion_within_48_hours(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())

            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1"},
                    "track": [
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 1",
                            "date": {"uts": "1770000000"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 2",
                            "date": {"uts": "1770003600"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770180001"},
                        },
                        {
                            "artist": {"#text": "Existing Artist"},
                            "album": {"#text": "Existing Album"},
                            "name": "Track 4",
                            "date": {"uts": "1770183601"},
                        },
                    ],
                }
            }

            mock_response = Mock()
            mock_response.json.return_value = lastfm_payload
            mock_response.raise_for_status.return_value = None

            mock_client = Mock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.get.return_value = mock_response

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=mock_client,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                review_response = client.get("/api/users/jacob/imports/review")
                history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 0)
        self.assertEqual(history_response.json()[0]["summary"]["review_candidates"], 0)
        self.assertEqual(review_response.json(), [])
