import tempfile
import unittest
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import ijson
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema, get_engine
from backend.app.models import (
    Album,
    AlbumMetadataCache,
    AlbumListen,
    ImportSession,
    ImportSessionLog,
    ImportedListeningEvent,
    SpotifyStreamingEvent,
    User,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services import import_service
from backend.app.services import spotify_catalog_service


SPOTIFY_IMPORT_REGRESSION_ZIP_ENV = "SPOTIFY_IMPORT_REGRESSION_ZIP"
SPOTIFY_IMPORT_REGRESSION_ZIP_FALLBACK = Path(
    "/Users/jacobbattenberg/Downloads/my_spotify_data.zip"
)
SPOTIFY_IMPORT_REGRESSION_MEMBER = (
    "Spotify Extended Streaming History/Streaming_History_Audio_2015.json"
)
SPOTIFY_IMPORT_REGRESSION_ARTIST = "Third Eye Blind"
SPOTIFY_IMPORT_REGRESSION_ALBUM = "Third Eye Blind"
SPOTIFY_IMPORT_REGRESSION_START = "2015-09-22T18:05:22Z"
SPOTIFY_IMPORT_REGRESSION_END = "2015-09-24T14:11:07Z"
SPOTIFY_IMPORT_REGRESSION_EXPECTED_ROWS = 23
SPOTIFY_IMPORT_REGRESSION_EXPECTED_UNIQUE_TRACKS = 10
SPOTIFY_IMPORT_REGRESSION_EXPECTED_LISTENED_AT = "2015-09-24T14:11:07Z"
SPOTIFY_IMPORT_REGRESSION_MAX_SECONDS = float(
    os.environ.get("SPOTIFY_IMPORT_REGRESSION_MAX_SECONDS", "2.0")
)


def spotify_import_regression_zip_path():
    configured_path = os.environ.get(SPOTIFY_IMPORT_REGRESSION_ZIP_ENV)
    if configured_path:
        path = Path(configured_path)
        return path if path.exists() else None
    return (
        SPOTIFY_IMPORT_REGRESSION_ZIP_FALLBACK
        if SPOTIFY_IMPORT_REGRESSION_ZIP_FALLBACK.exists()
        else None
    )


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

    def _album_listen_count(self, database_url, artist, album):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return (
                session.query(AlbumListen)
                .join(Album)
                .filter(Album.artist == artist, Album.name == album)
                .count()
            )

    def _album_row_count(self, database_url, artist, album):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return (
                session.query(Album)
                .filter(Album.artist == artist, Album.name == album)
                .count()
            )

    def _imported_events_for_album(self, database_url, artist, album):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return [
                {
                    "listened_at": row.listened_at,
                    "match_status": row.match_status,
                    "match_confidence": row.match_confidence,
                    "error_message": row.error_message,
                }
                for row in (
                    session.query(ImportedListeningEvent)
                    .filter(
                        ImportedListeningEvent.artist == artist,
                        ImportedListeningEvent.album == album,
                    )
                    .order_by(ImportedListeningEvent.listened_at)
                    .all()
                )
            ]

    def _import_log_count(self, database_url, import_session_id):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return (
                session.query(ImportSessionLog)
                .filter(ImportSessionLog.import_session_id == import_session_id)
                .count()
            )

    def _import_session_record(self, database_url, import_session_id):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            row = session.get(ImportSession, import_session_id)
            return {
                "original_filename": row.original_filename,
                "file_size_bytes": row.file_size_bytes,
                "file_sha256": row.file_sha256,
                "zip_member_count": row.zip_member_count,
                "duplicate_of_import_session_id": row.duplicate_of_import_session_id,
            }

    def _spotify_events_for_import(self, database_url, import_session_id):
        engine = get_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            return [
                {
                    "track_name": row.track_name,
                    "source_file": row.source_file,
                    "source_index": row.source_index,
                }
                for row in (
                    session.query(SpotifyStreamingEvent)
                    .filter(SpotifyStreamingEvent.import_session_id == import_session_id)
                    .order_by(SpotifyStreamingEvent.played_at, SpotifyStreamingEvent.id)
                    .all()
                )
            ]

    def _spotify_zip(self, files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, rows in files.items():
                archive.writestr(filename, json.dumps(rows))
        buffer.seek(0)
        return buffer

    def _spotify_regression_slice_zip(self, export_path):
        rows = []
        with zipfile.ZipFile(export_path) as archive:
            with archive.open(SPOTIFY_IMPORT_REGRESSION_MEMBER) as file_obj:
                for item in ijson.items(file_obj, "item"):
                    if (
                        item.get("master_metadata_album_artist_name")
                        == SPOTIFY_IMPORT_REGRESSION_ARTIST
                        and item.get("master_metadata_album_album_name")
                        == SPOTIFY_IMPORT_REGRESSION_ALBUM
                        and SPOTIFY_IMPORT_REGRESSION_START
                        <= (item.get("ts") or "")
                        <= SPOTIFY_IMPORT_REGRESSION_END
                    ):
                        rows.append(item)

        tracklist = sorted(
            {
                row.get("master_metadata_track_name")
                for row in rows
                if row.get("master_metadata_track_name")
            }
        )
        return (
            self._spotify_zip({SPOTIFY_IMPORT_REGRESSION_MEMBER: rows}),
            {
                "rows": len(rows),
                "tracklist": tracklist,
                "latest_played_at": max(row["ts"] for row in rows) if rows else None,
            },
        )

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

    def _spotify_catalog_tracks(
        self,
        rows,
        *,
        album_id="spotify-album-id",
        album_total_tracks=None,
        album_name=None,
        album_artist_name=None,
    ):
        resolved = {}
        for index, row in enumerate(rows, start=1):
            uri = row["spotify_track_uri"]
            resolved[uri] = import_service.spotify_catalog_service.SpotifyCatalogTrack(
                track_uri=uri,
                track_id=uri.removeprefix("spotify:track:"),
                track_name=row["master_metadata_track_name"],
                album_id=album_id,
                album_name=album_name or row["master_metadata_album_album_name"],
                album_artist_name=album_artist_name
                or row["master_metadata_album_artist_name"],
                album_total_tracks=album_total_tracks or len(rows),
                disc_number=1,
                track_number=index,
                album_images=[],
                album_release_date=None,
                raw_payload={},
            )
        return resolved

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
        self.assertIn("storing_streaming_events", summary["stage_timings"])
        self.assertIn("finalizing", summary["stage_timings"])
        self.assertIn(
            "2026-02-02T02:48:00Z",
            state_response.json()["completed_albums"]["Existing Artist - Existing Album"][
                "listen_history"
            ],
        )

    def test_spotify_import_stores_file_fingerprint_and_row_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            rows = self._spotify_rows()
            zip_file = self._spotify_zip({"nested/Streaming_History_Audio_0.json": rows})
            zip_bytes = zip_file.getvalue()
            expected_sha = hashlib.sha256(zip_bytes).hexdigest()

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("traceable.zip", zip_file, "application/zip")},
                )
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            history_response = client.get("/api/users/jacob/imports")
            session_record = self._import_session_record(database_url, import_session_id)
            spotify_events = self._spotify_events_for_import(database_url, import_session_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["original_filename"], "traceable.zip")
        self.assertEqual(response.json()["file_size_bytes"], len(zip_bytes))
        self.assertEqual(response.json()["file_sha256"], expected_sha)
        self.assertEqual(session_record["original_filename"], "traceable.zip")
        self.assertEqual(session_record["file_size_bytes"], len(zip_bytes))
        self.assertEqual(session_record["file_sha256"], expected_sha)
        self.assertEqual(session_record["zip_member_count"], 1)
        history_item = history_response.json()[0]
        self.assertEqual(history_item["original_filename"], "traceable.zip")
        self.assertEqual(history_item["file_sha256"], expected_sha)
        self.assertEqual(history_item["summary"]["spotify_import_sha256"], expected_sha)
        self.assertEqual(history_item["summary"]["spotify_import_zip_member_count"], 1)
        self.assertEqual(
            [(row["source_file"], row["source_index"]) for row in spotify_events],
            [
                ("nested/Streaming_History_Audio_0.json", 1),
                ("nested/Streaming_History_Audio_0.json", 2),
                ("nested/Streaming_History_Audio_0.json", 3),
                ("nested/Streaming_History_Audio_0.json", 4),
            ],
        )

    @unittest.skipUnless(
        spotify_import_regression_zip_path(),
        f"Set {SPOTIFY_IMPORT_REGRESSION_ZIP_ENV} to run the local Spotify ZIP regression.",
    )
    def test_spotify_zip_regression_slice_from_personal_export(self):
        export_path = spotify_import_regression_zip_path()
        zip_file, target = self._spotify_regression_slice_zip(export_path)
        self.assertEqual(target["rows"], SPOTIFY_IMPORT_REGRESSION_EXPECTED_ROWS)
        self.assertEqual(
            len(target["tracklist"]),
            SPOTIFY_IMPORT_REGRESSION_EXPECTED_UNIQUE_TRACKS,
        )
        self.assertEqual(
            target["latest_played_at"],
            SPOTIFY_IMPORT_REGRESSION_EXPECTED_LISTENED_AT,
        )

        seeded_state = {
            "last_checked": None,
            "albums_in_progress": {},
            "completed_albums": {
                f"{SPOTIFY_IMPORT_REGRESSION_ARTIST} - {SPOTIFY_IMPORT_REGRESSION_ALBUM}": {
                    "artist": SPOTIFY_IMPORT_REGRESSION_ARTIST,
                    "name": SPOTIFY_IMPORT_REGRESSION_ALBUM,
                    "source": "musicbrainz",
                    "listen_history": [],
                    "tracklist": [{"title": track} for track in target["tracklist"]],
                }
            },
            "most_recently_listened": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=seeded_state)

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                side_effect=spotify_catalog_service.SpotifyCatalogUnavailable("mocked"),
            ) as catalog_lookup, patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={
                        "file": (
                            "spotify-2015-third-eye-blind-session.zip",
                            zip_file,
                            "application/zip",
                        )
                    },
                )
                import_session_id = response.json()["import_session_id"]
                started_at = time.perf_counter()
                self._run_import_session(database_url, import_session_id)
                elapsed_seconds = time.perf_counter() - started_at
            history_response = client.get("/api/users/jacob/imports")
            state_response = client.get("/api/album-state")
            spotify_events = self._spotify_events_for_import(database_url, import_session_id)

        history_item = history_response.json()[0]
        summary = history_item["summary"]
        listen_history = state_response.json()["completed_albums"][
            f"{SPOTIFY_IMPORT_REGRESSION_ARTIST} - {SPOTIFY_IMPORT_REGRESSION_ALBUM}"
        ]["listen_history"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_item["status"], "completed")
        self.assertEqual(summary["total_rows"], SPOTIFY_IMPORT_REGRESSION_EXPECTED_ROWS)
        self.assertEqual(summary["new_event_rows"], 22)
        self.assertEqual(summary["duplicate_rows"], 1)
        self.assertEqual(summary["distinct_album_candidates"], 1)
        self.assertEqual(summary["matched_existing_rows"], 1)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(summary["spotify_catalog_fallback_rows"], 22)
        self.assertEqual(summary["musicbrainz_requests"], 0)
        self.assertEqual(summary["spotify_import_zip_member_count"], 1)
        self.assertIn("storing_streaming_events", summary["stage_timings"])
        self.assertIn("matching_cached_albums", summary["stage_timings"])
        self.assertEqual(listen_history, [SPOTIFY_IMPORT_REGRESSION_EXPECTED_LISTENED_AT])
        self.assertEqual(len(spotify_events), 22)
        self.assertTrue(
            all(
                row["source_file"] == SPOTIFY_IMPORT_REGRESSION_MEMBER
                for row in spotify_events
            )
        )
        self.assertGreaterEqual(min(row["source_index"] for row in spotify_events), 1)
        self.assertLessEqual(
            max(row["source_index"] for row in spotify_events),
            SPOTIFY_IMPORT_REGRESSION_EXPECTED_ROWS,
        )
        self.assertLess(elapsed_seconds, SPOTIFY_IMPORT_REGRESSION_MAX_SECONDS)
        catalog_lookup.assert_called_once()
        metadata_lookup.assert_not_called()

    def test_spotify_import_batches_large_raw_insert_under_sqlite_variable_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = [
                {
                    "ts": f"2026-02-{1 + index // 1000:02d}T02:{index % 60:02d}:00Z",
                    "ms_played": 180000,
                    "master_metadata_track_name": "Track 1",
                    "master_metadata_album_artist_name": "Batch Artist",
                    "master_metadata_album_album_name": "Batch Album",
                    "spotify_track_uri": f"spotify:track:batch:{index}",
                    "platform": "ios",
                    "conn_country": "US",
                }
                for index in range(2_100)
            ]
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("large.zip", zip_file, "application/zip")},
                )
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            history_response = client.get("/api/users/jacob/imports")
            spotify_event_count = self._spotify_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["status"], "completed")
        self.assertEqual(history_response.json()[0]["summary"]["new_event_rows"], 2_100)
        self.assertEqual(spotify_event_count, 2_100)

    def test_spotify_import_detects_duplicate_file_sha(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            rows = self._spotify_rows()
            first_zip = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            first_bytes = first_zip.getvalue()
            second_zip = io.BytesIO(first_bytes)
            first_sha = hashlib.sha256(first_bytes).hexdigest()

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                first_response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("first.zip", first_zip, "application/zip")},
                )
                first_id = first_response.json()["import_session_id"]
                self._run_import_session(database_url, first_id)
                second_response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("second.zip", second_zip, "application/zip")},
                )
            second_id = second_response.json()["import_session_id"]
            second_record = self._import_session_record(database_url, second_id)
            logs_response = client.get(
                f"/api/users/jacob/imports/{second_id}/logs?order=asc"
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["file_sha256"], first_sha)
        self.assertEqual(second_response.json()["duplicate_of_import_session_id"], first_id)
        self.assertEqual(second_record["duplicate_of_import_session_id"], first_id)
        self.assertTrue(
            any(entry["level"] == "warning" for entry in logs_response.json())
        )

    def test_spotify_import_similar_filename_with_different_hash_is_distinct(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            first_zip = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows(tracks=["Track 1"])}
            )
            second_zip = self._spotify_zip(
                {"Streaming_History_Audio_0.json": self._spotify_rows(tracks=["Track 2"])}
            )

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ):
                first_response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("my_spotify_data.zip", first_zip, "application/zip")},
                )
                self._run_import_session(database_url, first_response.json()["import_session_id"])
                second_response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("my_spotify_data (1).zip", second_zip, "application/zip")},
                )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertNotEqual(first_response.json()["file_sha256"], second_response.json()["file_sha256"])
        self.assertIsNone(second_response.json()["duplicate_of_import_session_id"])

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
            imported_event_count = self._imported_event_count(database_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 0)
        self.assertEqual(imported_event_count, 0)
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
                        tracks=[
                            "Track 1",
                            "Track 2",
                            "Track 3",
                            "Track 4",
                            "Track 5",
                            "Track 6",
                            "Track 7",
                            "Track 8",
                        ],
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
        self.assertEqual(spotify_event_count, 200)
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

    def test_spotify_import_skips_existing_album_listen_on_same_utc_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(
                temp_dir,
                state=sample_album_state_with_tracklist(),
            )
            overlapping_session = self._spotify_rows()
            later_session = self._spotify_rows()
            for index, row in enumerate(overlapping_session):
                row["ts"] = f"2026-04-01T12:{index:02d}:00Z"
            for index, row in enumerate(later_session):
                row["ts"] = f"2026-04-04T12:{index:02d}:00Z"
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": overlapping_session + later_session}
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
            processed_count = self._imported_event_count(database_url, "processed_album_listen")
            duplicate_count = self._imported_event_count(database_url, "duplicate_listen")
            listen_count = self._album_listen_count(
                database_url,
                "Existing Artist",
                "Existing Album",
            )
            album_count = self._album_row_count(
                database_url,
                "Existing Artist",
                "Existing Album",
            )

        listen_history = state_response.json()["completed_albums"][
            "Existing Artist - Existing Album"
        ]["listen_history"]
        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(spotify_event_count, 8)
        self.assertEqual(processed_count, 1)
        self.assertEqual(duplicate_count, 1)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(listen_count, 2)
        self.assertEqual(album_count, 1)
        self.assertEqual(
            listen_history,
            ["2026-04-01T10:00:00.000Z", "2026-04-04T12:03:00Z"],
        )

    def test_spotify_import_dedupes_musicbrainz_lookup_per_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            first_session = self._spotify_rows(
                artist="Remote Spotify Artist",
                album="Remote Spotify Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
            )
            second_session = self._spotify_rows(
                artist="Remote Spotify Artist",
                album="Remote Spotify Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
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
                    {"title": "Track 4"},
                    {"title": "Track 5"},
                    {"title": "Track 6"},
                    {"title": "Track 7"},
                    {"title": "Track 8"},
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
        summary = history_response.json()[0]["summary"]
        self.assertEqual(summary["metadata_lookup_total"], 1)
        self.assertEqual(summary["metadata_lookup_current"], 1)
        self.assertEqual(history_response.json()[0]["summary"]["derived_album_listens"], 2)

    def test_spotify_import_creates_review_for_strong_evidence_when_musicbrainz_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Review Spotify Artist",
                album="Review Spotify Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=None,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
                review_count = self._imported_event_count(database_url, "candidate_review")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(review_count, 1)
        summary = history_response.json()[0]["summary"]
        self.assertEqual(summary["review_candidates"], 1)
        self.assertEqual(summary["metadata_lookup_total"], 1)

    def test_spotify_import_rejects_partial_combined_musicbrainz_track(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=[
                    "Burnout",
                    "Having a Blast",
                    "Chump",
                    "Longview",
                    "Welcome to Paradise",
                    "Pulling Teeth",
                    "Basket Case",
                    "She",
                    "Sassafras Roots",
                    "When I Come Around",
                    "Coming Clean",
                    "Emenius Sleepus",
                    "In the End",
                    "F.O.D.",
                ],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            metadata = {
                "artist": "Green Day",
                "name": "Dookie",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [
                    {"title": "Burnout"},
                    {"title": "Having a Blast"},
                    {"title": "Chump"},
                    {"title": "Longview"},
                    {"title": "Welcome to Paradise"},
                    {"title": "Pulling Teeth"},
                    {"title": "Basket Case"},
                    {"title": "She"},
                    {"title": "Sassafras Roots"},
                    {"title": "When I Come Around"},
                    {"title": "Coming Clean"},
                    {"title": "Emenius Sleepus"},
                    {"title": "In the End"},
                    {"title": "F.O.D. / All by Myself"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            imported_events = self._imported_events_for_album(
                database_url,
                "Green Day",
                "Dookie",
            )
            listen_count = self._album_listen_count(database_url, "Green Day", "Dookie")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(listen_count, 0)
        self.assertEqual(imported_events[0]["match_status"], "partial_listen")
        self.assertIn("F.O.D. / All by Myself", imported_events[0]["error_message"])

    def test_spotify_catalog_total_prevents_partial_dookie_listen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=[
                    "Burnout",
                    "Having a Blast",
                    "Chump",
                    "Longview",
                    "Welcome to Paradise",
                    "Pulling Teeth",
                    "Basket Case",
                    "She",
                    "Sassafras Roots",
                    "When I Come Around",
                    "Coming Clean",
                    "Emenius Sleepus",
                    "In the End",
                    "F.O.D.",
                ],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            metadata = {
                "artist": "Green Day",
                "name": "Dookie",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [
                    {"title": "Burnout"},
                    {"title": "Having a Blast"},
                    {"title": "Chump"},
                    {"title": "Longview"},
                    {"title": "Welcome to Paradise"},
                    {"title": "Pulling Teeth"},
                    {"title": "Basket Case"},
                    {"title": "She"},
                    {"title": "Sassafras Roots"},
                    {"title": "When I Come Around"},
                    {"title": "Coming Clean"},
                    {"title": "Emenius Sleepus"},
                    {"title": "In the End"},
                    {"title": "F.O.D. / All by Myself"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                return_value=self._spotify_catalog_tracks(
                    rows,
                    album_id="spotify-dookie",
                    album_total_tracks=15,
                ),
            ) as catalog_lookup, patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            listen_count = self._album_listen_count(database_url, "Green Day", "Dookie")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(catalog_lookup.call_count, 1)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(summary["spotify_catalog_resolved_tracks"], 14)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(listen_count, 0)

    def test_spotify_import_accepts_complete_combined_musicbrainz_track_parts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=[
                    "Burnout",
                    "Having a Blast",
                    "Chump",
                    "Longview",
                    "Welcome to Paradise",
                    "Pulling Teeth",
                    "Basket Case",
                    "She",
                    "Sassafras Roots",
                    "When I Come Around",
                    "Coming Clean",
                    "Emenius Sleepus",
                    "In the End",
                    "F.O.D.",
                    "All by Myself",
                ],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            metadata = {
                "artist": "Green Day",
                "name": "Dookie",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [
                    {"title": "Burnout"},
                    {"title": "Having a Blast"},
                    {"title": "Chump"},
                    {"title": "Longview"},
                    {"title": "Welcome to Paradise"},
                    {"title": "Pulling Teeth"},
                    {"title": "Basket Case"},
                    {"title": "She"},
                    {"title": "Sassafras Roots"},
                    {"title": "When I Come Around"},
                    {"title": "Coming Clean"},
                    {"title": "Emenius Sleepus"},
                    {"title": "In the End"},
                    {"title": "F.O.D. / All by Myself"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            listen_count = self._album_listen_count(database_url, "Green Day", "Dookie")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(listen_count, 1)

    def test_spotify_catalog_total_creates_complete_dookie_listen_with_ambiguous_musicbrainz_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=[
                    "Burnout",
                    "Having a Blast",
                    "Chump",
                    "Longview",
                    "Welcome to Paradise",
                    "Pulling Teeth",
                    "Basket Case",
                    "She",
                    "Sassafras Roots",
                    "When I Come Around",
                    "Coming Clean",
                    "Emenius Sleepus",
                    "In the End",
                    "F.O.D.",
                    "All by Myself",
                ],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            metadata = {
                "artist": "Green Day",
                "name": "Dookie",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [
                    {"title": "Burnout"},
                    {"title": "Having a Blast"},
                    {"title": "Chump"},
                    {"title": "Longview"},
                    {"title": "Welcome to Paradise"},
                    {"title": "Pulling Teeth"},
                    {"title": "Basket Case"},
                    {"title": "She"},
                    {"title": "Sassafras Roots"},
                    {"title": "When I Come Around"},
                    {"title": "Coming Clean"},
                    {"title": "Emenius Sleepus"},
                    {"title": "In the End"},
                    {"title": "F.O.D. / All by Myself"},
                ],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                return_value=self._spotify_catalog_tracks(
                    rows,
                    album_id="spotify-dookie",
                    album_total_tracks=15,
                ),
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ) as metadata_lookup:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            listen_count = self._album_listen_count(database_url, "Green Day", "Dookie")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup.call_count, 1)
        self.assertEqual(summary["spotify_catalog_resolved_tracks"], 15)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(listen_count, 1)

    def test_spotify_import_keeps_threshold_for_ordinary_album_tracks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Threshold Artist",
                album="Threshold Album",
                tracks=[f"Track {index}" for index in range(1, 10)],
            )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            metadata = {
                "artist": "Threshold Artist",
                "name": "Threshold Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [{"title": f"Track {index}"} for index in range(1, 11)],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            listen_count = self._album_listen_count(
                database_url,
                "Threshold Artist",
                "Threshold Album",
            )

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(listen_count, 1)

    def test_spotify_catalog_groups_same_named_albums_by_spotify_album_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            first_rows = self._spotify_rows(
                artist="Same Artist",
                album="Same Album",
                tracks=["Track 1", "Track 2"],
            )
            second_rows = self._spotify_rows(
                artist="Same Artist",
                album="Same Album",
                tracks=["Other 1", "Other 2"],
            )
            for row in second_rows:
                row["spotify_track_uri"] = row["spotify_track_uri"].replace(
                    "Same Album",
                    "Same Album Other",
                )
            for index, row in enumerate(second_rows):
                row["ts"] = f"2026-02-02T03:{45 + index:02d}:00Z"
            rows = first_rows + second_rows
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            first_catalog = self._spotify_catalog_tracks(
                first_rows,
                album_id="spotify-same-album-1",
                album_total_tracks=2,
            )
            second_catalog = self._spotify_catalog_tracks(
                second_rows,
                album_id="spotify-same-album-2",
                album_total_tracks=2,
            )
            metadata = {
                "artist": "Same Artist",
                "name": "Same Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [{"title": "Track 1"}, {"title": "Track 2"}],
            }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                return_value={**first_catalog, **second_catalog},
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            processed_count = self._imported_event_count(database_url, "processed_album_listen")
            duplicate_count = self._imported_event_count(database_url, "duplicate_listen")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["distinct_album_candidates"], 2)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(processed_count, 1)
        self.assertEqual(duplicate_count, 1)

    def test_spotify_catalog_lookup_dedupes_repeated_track_uris(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Repeated Artist",
                album="Repeated Album",
                tracks=["Track 1", "Track 1", "Track 2"],
            )
            rows[1]["spotify_track_uri"] = rows[0]["spotify_track_uri"]
            rows[1]["ts"] = "2026-02-02T02:46:30Z"
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})
            catalog = self._spotify_catalog_tracks(
                [rows[0], rows[2]],
                album_id="spotify-repeated-album",
                album_total_tracks=2,
            )
            metadata = {
                "artist": "Repeated Artist",
                "name": "Repeated Album",
                "primary_type": "Album",
                "_musicbrainz_match": {"confidence": 93},
                "tracklist": [{"title": "Track 1"}, {"title": "Track 2"}],
            }
            seen_uris = []

            def resolve(track_uris):
                seen_uris.extend(track_uris)
                return catalog

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                side_effect=resolve,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                return_value=metadata,
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(seen_uris), 2)
        self.assertEqual(summary["spotify_catalog_resolved_tracks"], 2)
        self.assertEqual(summary["derived_album_listens"], 1)

    def test_spotify_catalog_partials_skip_metadata_lookup_and_persistence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = []
            catalog = {}
            for index in range(6):
                row = {
                    "ts": f"2026-02-02T02:{index:02d}:00Z",
                    "ms_played": 180000,
                    "master_metadata_track_name": "Only Track",
                    "master_metadata_album_artist_name": "Partial Artist",
                    "master_metadata_album_album_name": f"Partial Album {index}",
                    "spotify_track_uri": f"spotify:track:partial:{index}",
                    "platform": "ios",
                    "conn_country": "US",
                }
                rows.append(row)
                uri = row["spotify_track_uri"]
                catalog[uri] = import_service.spotify_catalog_service.SpotifyCatalogTrack(
                    track_uri=uri,
                    track_id=f"partial-track-{index}",
                    track_name="Only Track",
                    album_id=f"partial-album-{index}",
                    album_name=row["master_metadata_album_album_name"],
                    album_artist_name="Partial Artist",
                    album_total_tracks=10,
                    disc_number=1,
                    track_number=1,
                    album_images=[],
                    album_release_date=None,
                    raw_payload={},
                )
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.spotify_catalog_service.resolve_tracks_by_uri",
                return_value=catalog,
            ), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Spotify partials should not fetch metadata."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
                history_response = client.get("/api/users/jacob/imports")
            imported_event_count = self._imported_event_count(database_url)
            metadata_cache_count = self._metadata_cache_count(database_url)

        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary["distinct_album_candidates"], 6)
        self.assertEqual(summary["derived_album_listens"], 0)
        self.assertEqual(imported_event_count, 0)
        self.assertEqual(metadata_cache_count, 0)

    def test_spotify_candidate_progress_uses_coarse_intervals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                import_session = ImportSession(
                    user_id=repository.user.id,
                    source=import_service.SPOTIFY_IMPORT_SOURCE,
                    status="matching_cached_albums",
                    started_at="2026-02-02T00:00:00+00:00",
                    summary_json={},
                )
                session.add(import_session)
                session.flush()
                for index in range(1201):
                    session.add(
                        SpotifyStreamingEvent(
                            user_id=repository.user.id,
                            import_session_id=import_session.id,
                            event_fingerprint=f"progress-{index}",
                            played_at=f"2026-02-02T02:{index // 60:02d}:{index % 60:02d}Z",
                            ms_played=180000,
                            track_name="Only Track",
                            artist_name="Progress Artist",
                            album_name=f"Progress Album {index}",
                            spotify_track_uri=f"spotify:track:progress:{index}",
                            spotify_track_id=f"progress-track-{index}",
                            spotify_album_id=f"progress-album-{index}",
                            spotify_album_name=f"Progress Album {index}",
                            spotify_album_artist_name="Progress Artist",
                            spotify_album_total_tracks=10,
                            spotify_disc_number=1,
                            spotify_track_number=1,
                            spotify_catalog_status="resolved",
                            raw_payload={},
                        )
                    )
                session.commit()

                progress_calls = []
                with patch(
                    "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                    side_effect=AssertionError("Spotify partials should not fetch metadata."),
                ):
                    candidates = import_service._build_spotify_candidates_from_streaming_events(
                        session=session,
                        repository=repository,
                        import_session=import_session,
                        allow_remote_metadata=False,
                        progress_callback=lambda current, total, partial: progress_calls.append(
                            (current, total, len(partial))
                        ),
                    )

        self.assertEqual(len(candidates), 1201)
        self.assertTrue(all(candidate.status == "partial_listen" for candidate in candidates))
        self.assertEqual(
            [call[0] for call in progress_calls],
            [1, 500, 1000, 1201],
        )
        self.assertTrue(all(call[1] == 1201 for call in progress_calls))

    def test_spotify_import_diagnostics_reports_source_rows_and_missing_tracks(self):
        dookie_tracks = [
            "Burnout",
            "Having a Blast",
            "Chump",
            "Longview",
            "Welcome to Paradise",
            "Pulling Teeth",
            "Basket Case",
            "She",
            "Sassafras Roots",
            "When I Come Around",
            "Coming Clean",
            "Emenius Sleepus",
            "In the End",
            "F.O.D.",
            "All by Myself",
        ]
        state = sample_album_state()
        state["completed_albums"]["Green Day - Dookie"] = {
            "artist": "Green Day",
            "name": "Dookie",
            "source": "musicbrainz",
            "entry_source": "manual",
            "listen_history": [],
            "tracklist": [{"title": track} for track in dookie_tracks],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir, state=state)
            full_rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=dookie_tracks,
            )
            partial_rows = self._spotify_rows(
                artist="Green Day",
                album="Dookie",
                tracks=dookie_tracks[:-2],
            )
            for index, row in enumerate(partial_rows):
                row["ts"] = f"2026-03-05T02:{45 + index:02d}:00Z"
            zip_file = self._spotify_zip({"Streaming_History_Audio_0.json": full_rows + partial_rows})

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=AssertionError("Existing album tracklist should be reused."),
            ):
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("dookie.zip", zip_file, "application/zip")},
                )
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            diagnostics_response = client.get(
                f"/api/users/jacob/imports/{import_session_id}/diagnostics",
                params={"artist": "Green Day", "album": "Dookie"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(diagnostics_response.status_code, 200)
        diagnostics = diagnostics_response.json()
        self.assertEqual(diagnostics["original_filename"], "dookie.zip")
        self.assertEqual(diagnostics["raw_row_count"], 28)
        self.assertEqual(diagnostics["expected_tracks"], dookie_tracks)
        self.assertEqual(len(diagnostics["sessions"]), 2)
        full_session, partial_session = diagnostics["sessions"]
        self.assertTrue(full_session["listen_created"])
        self.assertEqual(full_session["missing_tracks"], [])
        self.assertEqual(full_session["rows"][0]["source_file"], "Streaming_History_Audio_0.json")
        self.assertEqual(full_session["rows"][0]["source_index"], 1)
        self.assertEqual(partial_session["missing_tracks"], ["F.O.D.", "All by Myself"])
        self.assertFalse(partial_session["listen_created"])
        self.assertEqual(partial_session["rows"][0]["source_index"], 16)

    def test_import_history_includes_step_progress_and_live_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            rows = self._spotify_rows(
                artist="Logged Spotify Artist",
                album="Logged Spotify Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
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
                import_session_id = response.json()["import_session_id"]
                self._run_import_session(database_url, import_session_id)
            history_response = client.get("/api/users/jacob/imports")
            logs_response = client.get(
                f"/api/users/jacob/imports/{import_session_id}/logs?order=asc"
            )
            log_count = self._import_log_count(database_url, import_session_id)

        self.assertEqual(history_response.status_code, 200)
        history_item = history_response.json()[0]
        self.assertEqual(history_item["current_step_key"], "finalize")
        self.assertEqual(
            [step["key"] for step in history_item["steps"]],
            [
                "store_source",
                "find_sessions",
                "check_saved",
                "lookup_missing",
                "finalize",
            ],
        )
        self.assertGreater(log_count, 0)
        self.assertEqual(logs_response.status_code, 200)
        log_messages = [entry["message"] for entry in logs_response.json()]
        self.assertIn("Spotify import queued.", log_messages)
        self.assertTrue(
            any("Checked Logged Spotify Artist - Logged Spotify Album" in message for message in log_messages)
        )

    def test_spotify_metadata_commits_each_unique_album_before_queue_finishes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(temp_dir)
            first_rows = self._spotify_rows(
                artist="First Remote Artist",
                album="First Remote Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
            )
            second_rows = self._spotify_rows(
                artist="Second Remote Artist",
                album="Second Remote Album",
                tracks=[
                    "Track 1",
                    "Track 2",
                    "Track 3",
                    "Track 4",
                    "Track 5",
                    "Track 6",
                    "Track 7",
                    "Track 8",
                ],
            )
            zip_file = self._spotify_zip(
                {"Streaming_History_Audio_0.json": first_rows + second_rows}
            )

            def metadata_lookup(artist, album):
                if artist == "Second Remote Artist":
                    self.assertEqual(
                        self._album_listen_count(
                            database_url,
                            "First Remote Artist",
                            "First Remote Album",
                        ),
                        1,
                    )
                return {
                    "artist": artist,
                    "name": album,
                    "primary_type": "Album",
                    "_musicbrainz_match": {"confidence": 91},
                    "tracklist": [{"title": f"Track {index}"} for index in range(1, 9)],
                }

            with patch("backend.app.routers.imports._start_import_background_worker"), patch(
                "backend.app.services.import_service.album_metadata_service.get_album_metadata_for_import_matching",
                side_effect=metadata_lookup,
            ) as metadata_lookup_mock:
                response = client.post(
                    "/api/users/jacob/imports/spotify/upload",
                    files={"file": ("spotify.zip", zip_file, "application/zip")},
                )
                self._run_import_session(database_url, response.json()["import_session_id"])
            first_listen_count = self._album_listen_count(
                database_url,
                "First Remote Artist",
                "First Remote Album",
            )
            second_listen_count = self._album_listen_count(
                database_url,
                "Second Remote Artist",
                "Second Remote Album",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata_lookup_mock.call_count, 2)
        self.assertEqual(first_listen_count, 1)
        self.assertEqual(second_listen_count, 1)

    def test_spotify_resume_without_zip_after_raw_events_are_stored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                import_session = ImportSession(
                    user_id=repository.user.id,
                    source="spotify_import",
                    source_user_id=None,
                    status="storing_streaming_events",
                    session_name="Resume stored Spotify rows",
                    started_at=import_service._utc_now(),
                    completed_at=None,
                    artifact_path=None,
                    summary_json=import_service._empty_summary().model_dump(),
                )
                session.add(import_session)
                session.flush()
                for row in self._spotify_rows():
                    session.add(
                        SpotifyStreamingEvent(
                            user_id=repository.user.id,
                            import_session_id=import_session.id,
                            event_fingerprint=hashlib.sha256(
                                json.dumps(row, sort_keys=True).encode("utf-8")
                            ).hexdigest(),
                            played_at=row["ts"],
                            ms_played=row["ms_played"],
                            spotify_track_uri=row["spotify_track_uri"],
                            track_name=row["master_metadata_track_name"],
                            artist_name=row["master_metadata_album_artist_name"],
                            album_name=row["master_metadata_album_album_name"],
                            platform=row["platform"],
                            country=row["conn_country"],
                            raw_payload=row,
                        )
                    )
                import_session_id = import_session.id
                session.commit()

                import_service.run_import_session(session, import_session_id)

            with session_factory() as session:
                finished = session.get(ImportSession, import_session_id)
                listen_count = session.query(AlbumListen).count()

        self.assertEqual(finished.status, "completed")
        self.assertEqual(listen_count, 2)

    def test_spotify_resume_processes_existing_raw_candidate_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir, state=sample_album_state_with_tracklist())
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                import_session = ImportSession(
                    user_id=repository.user.id,
                    source=import_service.SPOTIFY_IMPORT_SOURCE,
                    source_user_id=None,
                    status="matching_cached_albums",
                    session_name="Resume raw Spotify candidates",
                    started_at=import_service._utc_now(),
                    completed_at=None,
                    artifact_path=None,
                    summary_json=import_service._empty_summary().model_dump(),
                )
                session.add(import_session)
                session.flush()
                for row in self._spotify_rows():
                    session.add(
                        SpotifyStreamingEvent(
                            user_id=repository.user.id,
                            import_session_id=import_session.id,
                            event_fingerprint=hashlib.sha256(
                                json.dumps(row, sort_keys=True).encode("utf-8")
                            ).hexdigest(),
                            played_at=row["ts"],
                            ms_played=row["ms_played"],
                            spotify_track_uri=row["spotify_track_uri"],
                            track_name=row["master_metadata_track_name"],
                            artist_name=row["master_metadata_album_artist_name"],
                            album_name=row["master_metadata_album_album_name"],
                            platform=row["platform"],
                            country=row["conn_country"],
                            raw_payload=row,
                        )
                    )
                session.flush()
                import_service._build_spotify_candidates_from_streaming_events(
                    session=session,
                    repository=repository,
                    import_session=import_session,
                    allow_remote_metadata=False,
                )
                import_session_id = import_session.id
                self.assertEqual(
                    session.query(ImportedListeningEvent)
                    .filter(
                        ImportedListeningEvent.import_session_id == import_session_id,
                        ImportedListeningEvent.match_status == "raw_imported",
                    )
                    .count(),
                    1,
                )
                session.commit()

                import_service.run_import_session(session, import_session_id)

            with session_factory() as session:
                finished = session.get(ImportSession, import_session_id)
                statuses = {
                    status: count
                    for status, count in (
                        session.query(
                            ImportedListeningEvent.match_status,
                            func.count(),
                        )
                        .filter(ImportedListeningEvent.import_session_id == import_session_id)
                        .group_by(ImportedListeningEvent.match_status)
                        .all()
                    )
                }
                listen_count = (
                    session.query(AlbumListen)
                    .join(Album)
                    .filter(Album.artist == "Existing Artist", Album.name == "Existing Album")
                    .count()
                )

        self.assertEqual(finished.status, "completed")
        self.assertEqual(statuses, {"processed_album_listen": 1})
        self.assertEqual(finished.summary_json["derived_album_listens"], 1)
        self.assertEqual(listen_count, 2)

    def test_repair_spotify_import_processes_completed_raw_candidate_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                metadata = {
                    "artist": "Repair Artist",
                    "name": "Repair Album",
                    "primary_type": "Album",
                    "_musicbrainz_match": {"confidence": 93},
                    "tracklist": [{"title": f"Track {index}"} for index in range(1, 5)],
                }
                session.add(
                    AlbumMetadataCache(
                        cache_key=import_service._album_metadata_cache_key(
                            "Repair Artist",
                            "Repair Album",
                        ),
                        artist="Repair Artist",
                        album="Repair Album",
                        status="matched",
                        metadata_json=metadata,
                        updated_at=import_service._utc_now(),
                    )
                )
                import_session = ImportSession(
                    user_id=repository.user.id,
                    source=import_service.SPOTIFY_IMPORT_SOURCE,
                    source_user_id=None,
                    status="completed",
                    session_name="Repair raw Spotify candidates",
                    started_at=import_service._utc_now(),
                    completed_at=import_service._utc_now(),
                    artifact_path=None,
                    summary_json={
                        **import_service._empty_summary().model_dump(),
                        "derived_album_listens": 1,
                    },
                )
                session.add(import_session)
                session.flush()
                for row in self._spotify_rows(
                    artist="Repair Artist",
                    album="Repair Album",
                    tracks=["Track 1", "Track 2", "Track 3", "Track 4"],
                ):
                    session.add(
                        SpotifyStreamingEvent(
                            user_id=repository.user.id,
                            import_session_id=import_session.id,
                            event_fingerprint=hashlib.sha256(
                                json.dumps(row, sort_keys=True).encode("utf-8")
                            ).hexdigest(),
                            played_at=row["ts"],
                            ms_played=row["ms_played"],
                            spotify_track_uri=row["spotify_track_uri"],
                            track_name=row["master_metadata_track_name"],
                            artist_name=row["master_metadata_album_artist_name"],
                            album_name=row["master_metadata_album_album_name"],
                            platform=row["platform"],
                            country=row["conn_country"],
                            raw_payload=row,
                        )
                    )
                session.flush()
                import_service._build_spotify_candidates_from_streaming_events(
                    session=session,
                    repository=repository,
                    import_session=import_session,
                    allow_remote_metadata=False,
                )
                import_session.status = "completed"
                import_session.completed_at = import_service._utc_now()
                import_session_id = import_session.id
                session.commit()

                first_summary = import_service.repair_spotify_import_session(
                    session,
                    repository,
                    import_session_id,
                )
                second_summary = import_service.repair_spotify_import_session(
                    session,
                    repository,
                    import_session_id,
                )
                listen_count = (
                    session.query(AlbumListen)
                    .join(Album)
                    .filter(Album.artist == "Repair Artist", Album.name == "Repair Album")
                    .count()
                )
                raw_remaining = (
                    session.query(ImportedListeningEvent)
                    .filter(
                        ImportedListeningEvent.import_session_id == import_session_id,
                        ImportedListeningEvent.match_status == "raw_imported",
                    )
                    .count()
                )

        self.assertEqual(first_summary.status, "completed")
        self.assertEqual(second_summary.status, "completed")
        self.assertEqual(first_summary.summary.derived_album_listens, 1)
        self.assertEqual(second_summary.summary.derived_album_listens, 1)
        self.assertEqual(listen_count, 1)
        self.assertEqual(raw_remaining, 0)

    def test_repair_spotify_import_refuses_wrong_source_or_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                lastfm_session = ImportSession(
                    user_id=repository.user.id,
                    source="lastfm",
                    status="completed",
                    started_at=import_service._utc_now(),
                    completed_at=import_service._utc_now(),
                    summary_json=import_service._empty_summary().model_dump(),
                )
                other_user = User(slug="other-user", display_name="Other User")
                session.add_all([lastfm_session, other_user])
                session.flush()
                other_session = ImportSession(
                    user_id=other_user.id,
                    source=import_service.SPOTIFY_IMPORT_SOURCE,
                    status="completed",
                    started_at=import_service._utc_now(),
                    completed_at=import_service._utc_now(),
                    summary_json=import_service._empty_summary().model_dump(),
                )
                session.add(other_session)
                session.commit()

                with self.assertRaisesRegex(ValueError, "Only Spotify"):
                    import_service.repair_spotify_import_session(
                        session,
                        repository,
                        lastfm_session.id,
                    )
                with self.assertRaisesRegex(KeyError, "Import session not found"):
                    import_service.repair_spotify_import_session(
                        session,
                        repository,
                        other_session.id,
                    )

    def test_spotify_resume_without_zip_before_raw_storage_fails_clearly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, database_url = self._client(temp_dir)
            engine = get_engine(database_url)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with session_factory() as session:
                repository = SqliteStateRepository(session)
                import_session = ImportSession(
                    user_id=repository.user.id,
                    source="spotify_import",
                    source_user_id=None,
                    status="queued",
                    session_name="Missing ZIP",
                    started_at=import_service._utc_now(),
                    completed_at=None,
                    artifact_path=None,
                    summary_json=import_service._empty_summary().model_dump(),
                )
                session.add(import_session)
                session.commit()
                import_session_id = import_session.id

                with self.assertRaisesRegex(ValueError, "re-upload is required"):
                    import_service.run_import_session(session, import_session_id)
                failed = session.get(ImportSession, import_session_id)

        self.assertEqual(failed.status, "failed")

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

    def test_lastfm_import_skips_existing_album_listen_on_same_utc_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, database_url = self._client(
                temp_dir,
                state=sample_album_state_with_tracklist(),
            )
            tracks = ["Track 1", "Track 2", "Track 3", "Track 4"]
            overlapping_start = int(
                import_service._parse_timestamp("2026-04-01T12:00:00Z").timestamp()
            )
            later_start = int(
                import_service._parse_timestamp("2026-04-04T12:00:00Z").timestamp()
            )
            overlapping_payload = self._lastfm_payload(
                "Existing Artist",
                "Existing Album",
                tracks,
                start_uts=overlapping_start,
            )
            later_payload = self._lastfm_payload(
                "Existing Artist",
                "Existing Album",
                tracks,
                start_uts=later_start,
            )
            lastfm_payload = {
                "recenttracks": {
                    "@attr": {"page": "1", "totalPages": "1", "total": "8"},
                    "track": (
                        overlapping_payload["recenttracks"]["track"]
                        + later_payload["recenttracks"]["track"]
                    ),
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
            state_response = client.get("/api/album-state")
            imported_event_count = self._imported_event_count(database_url)
            processed_count = self._imported_event_count(database_url, "processed_album_listen")
            duplicate_count = self._imported_event_count(database_url, "duplicate_listen")
            listen_count = self._album_listen_count(
                database_url,
                "Existing Artist",
                "Existing Album",
            )
            album_count = self._album_row_count(
                database_url,
                "Existing Artist",
                "Existing Album",
            )

        listen_history = state_response.json()["completed_albums"][
            "Existing Artist - Existing Album"
        ]["listen_history"]
        summary = history_response.json()[0]["summary"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(imported_event_count, 8)
        self.assertEqual(processed_count, 4)
        self.assertEqual(duplicate_count, 4)
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(listen_count, 2)
        self.assertEqual(album_count, 1)
        self.assertEqual(
            listen_history,
            ["2026-04-01T10:00:00.000Z", "2026-04-04T12:03:00+00:00"],
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
        summary = history_response.json()[0]["summary"]
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(summary["final_album_count"], 1)
        self.assertEqual(summary["pending_metadata_candidates"], 0)
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
        summary = history_response.json()[0]["summary"]
        self.assertEqual(summary["derived_album_listens"], 1)
        self.assertEqual(summary["final_album_count"], 1)
        self.assertGreaterEqual(summary["metadata_cache_hits"], 1)
        self.assertIsNone(summary["musicbrainz_lookup_seconds_avg"])

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
        summary = history_response.json()[0]["summary"]
        self.assertEqual(summary["derived_album_listens"], 2)
        self.assertEqual(summary["final_album_count"], 1)
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
