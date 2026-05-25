import tempfile
import unittest
import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema, get_engine
from backend.app.models import AlbumMetadataCache, ImportedListeningEvent, SpotifyStreamingEvent
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


def sample_single_track_album_state():
    state = sample_album_state()
    state["completed_albums"]["Existing Artist - Existing Album"]["tracklist"] = [
        {"title": "Track 1"},
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

    def _metadata_cache_count(self, database_url):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return session.query(AlbumMetadataCache).count()

    def _spotify_event_count(self, database_url):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return session.query(SpotifyStreamingEvent).count()

    def _spotify_zip(self, files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, rows in files.items():
                archive.writestr(filename, json.dumps(rows))
        buffer.seek(0)
        return buffer

    def _spotify_rows(self, artist="Existing Artist", album="Existing Album", tracks=None):
        tracks = tracks or ["Track 1", "Track 2", "Track 3", "Track 4"]
        return [
            {
                "ts": f"2026-02-02T02:{45 + index:02d}:00Z",
                "ms_played": 180000,
                "master_metadata_track_name": track,
                "master_metadata_album_artist_name": artist,
                "master_metadata_album_album_name": album,
                "spotify_track_uri": f"spotify:track:{artist}:{album}:{index}",
                "platform": "ios",
                "conn_country": "US",
            }
            for index, track in enumerate(tracks)
        ]

    def _lastfm_payload(self, artist, album, tracks, start_uts=1770000000):
        return {
            "recenttracks": {
                "@attr": {"page": "1", "totalPages": "1", "total": str(len(tracks))},
                "track": [
                    {
                        "artist": {"#text": artist},
                        "album": {"#text": album},
                        "name": track,
                        "date": {"uts": str(start_uts + index * 60)},
                    }
                    for index, track in enumerate(tracks)
                ],
            }
        }

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

    def test_spotify_zip_upload_returns_queued_session_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            zip_file = self._spotify_zip(
                {"Spotify Extended Streaming History/Streaming_History_Audio_2026_0.json": []}
            )

            with patch("backend.app.routers.imports._start_import_background_worker") as start_worker:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "spotify_import")
        self.assertEqual(response.json()["status"], "queued")
        start_worker.assert_called_once_with(response.json()["import_session_id"])
        self.assertEqual(history_response.json()[0]["status"], "queued")

    def test_spotify_zip_rejects_non_zip_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            response = client.post(
                "/api/users/jacob/imports/spotify/upload",
                files={"file": ("history.txt", io.BytesIO(b"not a zip"), "text/plain")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn(".zip", response.json()["detail"])

    def test_spotify_zip_rejects_oversized_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)
            with patch.dict("os.environ", {"SPOTIFY_IMPORT_MAX_ZIP_BYTES": "10"}):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={
                        "file": (
                            "spotify.zip",
                            self._spotify_zip({"Streaming_History_Audio_0.json": []}),
                            "application/zip",
                        )
                    },
                )

        self.assertEqual(response.status_code, 422)
        self.assertIn("too large", response.json()["detail"])

    def test_spotify_zip_rejects_missing_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self._client(temp_dir)

            response = client.post(
                "/api/users/missing/imports/spotify/upload",
                files={
                    "file": (
                        "spotify.zip",
                        self._spotify_zip({"Streaming_History_Audio_0.json": []}),
                        "application/zip",
                    )
                },
            )

        self.assertEqual(response.status_code, 404)

    def test_spotify_background_import_rejects_path_traversal_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("../Streaming_History_Audio_0.json", "[]")
            buffer.seek(0)

            with patch("backend.app.routers.imports._start_import_background_worker"):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", buffer, "application/zip")},
                )
                with self.assertRaises(ValueError):
                    self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "failed")

    def test_spotify_background_import_rejects_zip_bomb(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows() * 50
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch.dict(
                "os.environ",
                {"SPOTIFY_IMPORT_MAX_UNCOMPRESSED_BYTES": "100"},
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                with self.assertRaises(ValueError):
                    self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "failed")

    def test_spotify_background_import_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("Streaming_History_Audio_0.json", "{")
            buffer.seek(0)

            with patch("backend.app.routers.imports._start_import_background_worker"):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", buffer, "application/zip")},
                )
                with self.assertRaises(ValueError):
                    self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "failed")

    def test_spotify_background_import_stores_events_and_derives_album_listen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows()}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")
            state_response = client.get("/api/album-state")
            spotify_event_count = self._spotify_event_count(database_url)
            imported_event_count = self._imported_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(spotify_event_count, 4)
        self.assertEqual(imported_event_count, 1)
        summary = history_response.json()[0]["summary"]
        self.assertEqual(history_response.json()[0]["status"], "completed")
        self.assertEqual(summary["new_event_rows"], 4)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertIn(
            "2026-02-02T02:48:00Z",
            state_response.json()["completed_albums"]["Existing Artist - Existing Album"][
                "listen_history"
            ],
        )

    def test_spotify_background_import_deduplicates_uri_and_name_fallback_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            rows = self._spotify_rows()
            duplicate_uri = dict(rows[0])
            fallback = dict(rows[1])
            fallback.pop("spotify_track_uri")
            duplicate_fallback = dict(fallback)
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": rows + [duplicate_uri, fallback, duplicate_fallback]}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")
            spotify_event_count = self._spotify_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(spotify_event_count, 5)
        self.assertEqual(history_response.json()[0]["summary"]["duplicate_rows"], 2)

    def test_spotify_background_import_keeps_partial_session_out_of_album_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows(tracks=["Track 1"])}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")
            state_response = client.get("/api/album-state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 0)
        self.assertEqual(
            state_response.json()["completed_albums"]["Existing Artist - Existing Album"][
                "listen_history"
            ],
            ["2026-04-01T10:00:00.000Z"],
        )

    def test_spotify_import_creates_session_rows_not_per_play_import_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            rows = []
            for album_index in range(25):
                rows.extend(
                    self._spotify_rows(
                        artist=f"Bulk Artist {album_index}",
                        album=f"Bulk Album {album_index}",
                        tracks=["Track 1", "Track 2", "Track 3", "Track 4"],
                    )
                )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                spotify_event_count = self._spotify_event_count(database_url)
                imported_event_count = self._imported_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(spotify_event_count, 100)
        self.assertEqual(imported_event_count, 25)

    def test_spotify_import_can_create_multiple_album_listens_for_split_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            first_session = self._spotify_rows()
            second_session = self._spotify_rows()
            for index, row in enumerate(second_session):
                row["ts"] = f"2026-02-05T02:{45 + index:02d}:00Z"
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": first_session + second_session}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            state_response = client.get("/api/album-state")

        listen_history = state_response.json()["completed_albums"][
            "Existing Artist - Existing Album"
        ]["listen_history"]
        self.assertEqual(response.status_code, 200)
        self.assertIn("2026-02-02T02:48:00Z", listen_history)
        self.assertIn("2026-02-05T02:48:00Z", listen_history)

    def test_spotify_import_dedupes_musicbrainz_lookup_per_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            first_session = self._spotify_rows(
                artist="Remote Spotify Artist",
                album="Remote Spotify Album",
                tracks=["Track 1", "Track 2", "Track 3"],
            )
            second_session = self._spotify_rows(
                artist="Remote Spotify Artist",
                album="Remote Spotify Album",
                tracks=["Track 1", "Track 2", "Track 3"],
            )
            for index, row in enumerate(second_session):
                row["ts"] = f"2026-02-05T02:{45 + index:02d}:00Z"
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": first_session + second_session}
            )
            metadata = {
                "artist": "Remote Spotify Artist",
                "name": "Remote Spotify Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 91},
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 2)

    def test_delete_spotify_import_removes_raw_events_and_imported_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows()}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            delete_response = client.delete(f"/api/users/jacob/imports/{import_session_id}")
            state_response = client.get("/api/album-state")
            spotify_event_count = self._spotify_event_count(database_url)

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["deleted_events"], 1)
        self.assertEqual(delete_response.json()["deleted_listens"], 1)
        self.assertEqual(spotify_event_count, 0)
        self.assertEqual(
            state_response.json()["completed_albums"]["Existing Artist - Existing Album"][
                "listen_history"
            ],
            ["2026-04-01T10:00:00.000Z"],
        )

    def test_spotify_import_delete_is_user_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            client.post("/api/users", json={"slug": "test-user", "display_name": "Test User"})
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows()}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"):
                response = client.post(
                    "/api/users/test-user/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            delete_response = client.delete(f"/api/users/jacob/imports/{import_session_id}")
            test_history_response = client.get("/api/users/test-user/imports")
            spotify_event_count = self._spotify_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(test_history_response.json()[0]["id"], import_session_id)
        self.assertEqual(spotify_event_count, 4)

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

    def test_lastfm_commit_deduplicates_duplicate_rows_in_same_fetch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            tracks = [
                {
                    "artist": {"#text": "Existing Artist"},
                    "album": {"#text": "Existing Album"},
                    "name": f"Track {track_number}",
                    "date": {"uts": str(1770000000 + index * 100)},
                }
                for index, track_number in enumerate([1, 2, 3, 4])
            ]
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1", "total": "8"},
                    "track": tracks + tracks,
                }
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
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

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["new_event_rows"], 4)
        self.assertEqual(summary["duplicate_rows"], 4)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(imported_event_count, 4)

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
                        {
                            "artist": {"#text": "Unknown Artist"},
                            "album": {"#text": "Unknown Album"},
                            "name": "Track 3",
                            "date": {"uts": "1770000200"},
                        },
                    ],
                }
            }
            mock_client = self._mock_lastfm_client(lastfm_payload)

            def return_no_metadata(_artist, _album):
                self.assertEqual(
                    self._imported_event_count(database_url, "pending_metadata"),
                    3,
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

    def test_lastfm_commit_reports_api_error_payload_as_failed_import(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = {"error": 6, "message": "User not found"}

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "missing-user"},
                )
                with self.assertRaisesRegex(ValueError, "User not found"):
                    self._run_import_session(database_url, response.json()["import_session_id"])
            history_response = client.get("/api/users/jacob/imports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "failed")

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

    def test_lastfm_commit_skips_remote_metadata_for_one_track_uncached_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Low Evidence Artist",
                "Low Evidence Album",
                ["Only Track"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Low-evidence candidates should not call MusicBrainz."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                review_response = client.get("/api/users/jacob/imports/review")
                partial_listen_count = self._imported_event_count(database_url, "partial_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertEqual(summary["pending_metadata_candidates"], 0)
        self.assertEqual(partial_listen_count, 1)
        self.assertEqual(review_response.json(), [])

    def test_lastfm_commit_skips_remote_metadata_for_two_track_uncached_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Two Track Artist",
                "Two Track Album",
                ["Track 1", "Track 2"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Low-evidence candidates should not call MusicBrainz."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                review_response = client.get("/api/users/jacob/imports/review")
                partial_listen_count = self._imported_event_count(database_url, "partial_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertEqual(summary["pending_metadata_candidates"], 0)
        self.assertEqual(partial_listen_count, 2)
        self.assertEqual(review_response.json(), [])

    def test_lastfm_commit_fetches_remote_metadata_for_three_track_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Remote Artist",
                "Remote Album",
                ["Track 1", "Track 2", "Track 3"],
            )
            metadata = {
                "artist": "Remote Artist",
                "name": "Remote Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 91},
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                state_response = client.get("/api/users/jacob/album-state")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertIn("Remote Artist - Remote Album", state_response.json()["completed_albums"])

    def test_lastfm_commit_does_not_auto_create_from_low_confidence_musicbrainz_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Low Confidence Artist",
                "Low Confidence Album",
                ["Track 1", "Track 2", "Track 3"],
            )
            metadata = {
                "artist": "Low Confidence Artist",
                "name": "Low Confidence Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 60},
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
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
                partial_listen_count = self._imported_event_count(database_url, "partial_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertEqual(partial_listen_count, 3)
        self.assertNotIn(
            "Low Confidence Artist - Low Confidence Album",
            state_response.json()["completed_albums"],
        )

    def test_lastfm_commit_does_not_negative_cache_transient_musicbrainz_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            first_payload = self._lastfm_payload(
                "Flaky Artist",
                "Flaky Album",
                ["Track 1", "Track 2", "Track 3"],
                start_uts=1770000000,
            )
            second_payload = self._lastfm_payload(
                "Flaky Artist",
                "Flaky Album",
                ["Track 1", "Track 2", "Track 3"],
                start_uts=1770100000,
            )
            metadata = {
                "artist": "Flaky Artist",
                "name": "Flaky Album",
                "primary_type": "Album",
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(first_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=RuntimeError("temporary MusicBrainz failure"),
            ):
                first_response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, first_response.json()["import_session_id"])
            cache_count_after_failure = self._metadata_cache_count(database_url)

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(second_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                second_response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, second_response.json()["import_session_id"])
            state_response = client.get("/api/users/jacob/album-state")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(cache_count_after_failure, 0)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertIn("Flaky Artist - Flaky Album", state_response.json()["completed_albums"])

    def test_lastfm_commit_does_not_derive_album_listen_from_musicbrainz_single(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Single Artist",
                "Single Release",
                ["Track 1", "Track 2", "Track 3"],
            )
            metadata = {
                "artist": "Single Artist",
                "name": "Single Release",
                "primary_type": "Single",
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
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
                partial_listen_count = self._imported_event_count(database_url, "partial_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertEqual(partial_listen_count, 3)
        self.assertNotIn("Single Artist - Single Release", state_response.json()["completed_albums"])

    def test_lastfm_commit_does_not_derive_album_listen_from_cached_one_track_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                import_service._write_album_metadata_cache(
                    session,
                    "Cached Single Artist",
                    "Cached Single",
                    {
                        "artist": "Cached Single Artist",
                        "name": "Cached Single",
                        "tracklist": [
                            {"title": "Only Track"},
                        ],
                    },
                )
                session.commit()

            lastfm_payload = self._lastfm_payload(
                "Cached Single Artist",
                "Cached Single",
                ["Only Track"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Cached low-track metadata should not call MusicBrainz."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                state_response = client.get("/api/users/jacob/album-state")
                partial_listen_count = self._imported_event_count(database_url, "partial_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertEqual(partial_listen_count, 1)
        self.assertNotIn(
            "Cached Single Artist - Cached Single",
            state_response.json()["completed_albums"],
        )

    def test_lastfm_commit_uses_existing_one_track_album_without_musicbrainz_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_single_track_album_state())
            lastfm_payload = self._lastfm_payload(
                "Existing Artist",
                "Existing Album",
                ["Track 1"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
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
                processed_listen_count = self._imported_event_count(
                    database_url,
                    "processed_album_listen",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 1)
        self.assertEqual(processed_listen_count, 1)

    def test_lastfm_commit_uses_cached_metadata_below_remote_lookup_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                import_service._write_album_metadata_cache(
                    session,
                    "Cached Artist",
                    "Cached Album",
                    {
                        "artist": "Cached Artist",
                        "name": "Cached Album",
                        "primary_type": "Album",
                        "tracklist": [
                            {"title": "Track 1"},
                            {"title": "Track 2"},
                        ],
                    },
                )
                session.commit()

            lastfm_payload = self._lastfm_payload(
                "Cached Artist",
                "Cached Album",
                ["Track 1", "Track 2"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Cached metadata should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                state_response = client.get("/api/users/jacob/album-state")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(summary["review_candidates"], 0)
        self.assertIn("Cached Artist - Cached Album", state_response.json()["completed_albums"])

    def test_lastfm_commit_uses_not_found_metadata_cache_without_remote_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                import_service._write_album_metadata_cache(
                    session,
                    "Missing Metadata Artist",
                    "Missing Metadata Album",
                    None,
                )
                session.commit()

            lastfm_payload = self._lastfm_payload(
                "Missing Metadata Artist",
                "Missing Metadata Album",
                ["Track 1", "Track 2", "Track 3"],
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Negative metadata cache should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                review_response = client.get("/api/users/jacob/imports/review")
                review_count = self._imported_event_count(database_url, "candidate_review")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(summary["review_candidates"], 1)
        self.assertEqual(review_count, 3)
        self.assertEqual(len(review_response.json()), 1)

    def test_lastfm_commit_ignores_legacy_negative_metadata_cache_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            artist = "Legacy Cache Artist"
            album = "Legacy Cache Album"
            legacy_cache_key = hashlib.sha256(
                "|".join(
                    ["musicbrainz-import", artist.casefold(), album.casefold()]
                ).encode("utf-8")
            ).hexdigest()
            with session_factory() as session:
                session.add(
                    AlbumMetadataCache(
                        cache_key=legacy_cache_key,
                        artist=artist,
                        album=album,
                        status="not_found",
                        metadata_json={},
                        error_message="Legacy negative cache row.",
                        updated_at="2026-01-01T00:00:00+00:00",
                    )
                )
                session.commit()

            lastfm_payload = self._lastfm_payload(
                artist,
                album,
                ["Track 1", "Track 2", "Track 3"],
            )
            metadata = {
                "artist": artist,
                "name": album,
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 90},
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                state_response = client.get("/api/users/jacob/album-state")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertIn(f"{artist} - {album}", state_response.json()["completed_albums"])

    def test_resolving_one_review_album_resolves_all_unresolved_sessions_for_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            lastfm_payload = self._lastfm_payload(
                "Repeated Review Artist",
                "Repeated Review Album",
                ["Track 1", "Track 2", "Track 3"],
                start_uts=1770000000,
            )
            lastfm_payload["recenttracks"]["track"].extend(
                self._lastfm_payload(
                    "Repeated Review Artist",
                    "Repeated Review Album",
                    ["Track 1", "Track 2", "Track 3"],
                    start_uts=1770200000,
                )["recenttracks"]["track"]
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.lastfm_import_client.httpx.Client",
                return_value=self._mock_lastfm_client(lastfm_payload),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ):
                response = client.post(
                    "/api/users/jacob/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "jacobfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                review_response = client.get("/api/users/jacob/imports/review")
                state_response = client.get("/api/users/jacob/album-state")

                album_id = state_response.json()["completed_albums"][
                    "Existing Artist - Existing Album"
                ]["id"]
                resolve_response = client.post(
                    f"/api/users/jacob/imports/review/{review_response.json()[0]['id']}/resolve",
                    json={"existing_album_id": album_id},
                )
                resolved_review_response = client.get("/api/users/jacob/imports/review")
                resolved_state_response = client.get("/api/users/jacob/album-state")
                resolved_event_count = self._imported_event_count(database_url, "resolved")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(len(review_response.json()), 1)
        self.assertEqual(resolve_response.status_code, 200)
        self.assertEqual(resolved_review_response.json(), [])
        self.assertEqual(resolved_event_count, 6)
        listen_history = resolved_state_response.json()["completed_albums"][
            "Existing Artist - Existing Album"
        ]["listen_history"]
        self.assertEqual(len(listen_history), 3)

    def test_lastfm_import_for_test_user_does_not_mutate_jacob(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            create_user_response = client.post(
                "/api/users",
                json={"slug": "test", "display_name": "Test"},
            )
            lastfm_payload = self._lastfm_payload(
                "Test Import Artist",
                "Test Import Album",
                ["Track 1", "Track 2", "Track 3"],
            )
            metadata = {
                "artist": "Test Import Artist",
                "name": "Test Import Album",
                "primary_type": "Album",
                "tracklist": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
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
                    "/api/users/test/imports/commit",
                    json={"source": "lastfm", "lastfm_username": "testfm"},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            jacob_state = client.get("/api/users/jacob/album-state").json()
            test_state = client.get("/api/users/test/album-state").json()
            jacob_history = client.get("/api/users/jacob/imports").json()
            jacob_review = client.get("/api/users/jacob/imports/review").json()

        self.assertEqual(create_user_response.status_code, 201)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "Test Import Artist - Test Import Album",
            jacob_state["completed_albums"],
        )
        self.assertIn(
            "Test Import Artist - Test Import Album",
            test_state["completed_albums"],
        )
        self.assertEqual(jacob_history, [])
        self.assertEqual(jacob_review, [])
