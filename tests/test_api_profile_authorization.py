import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.database import create_schema
from backend.app.main import create_app


class ProfileAuthorizationApiTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        create_schema(database_url)
        patcher = patch.dict(
            "os.environ",
            {"DATABASE_URL": database_url, "MEDIA_DIR": temp_dir, "DATA_DIR": temp_dir},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def _create_profile(self, client, *, slug, email):
        response = client.post(
            "/api/users",
            json={
                "slug": slug,
                "display_name": slug.title(),
                "email": email,
                "password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(response.status_code, 201)
        return {"Authorization": f"Bearer {response.json()['session_token']}"}

    def test_public_and_cross_account_requests_cannot_mutate_a_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            owner_headers = self._create_profile(
                client, slug="owner", email="owner@example.com"
            )
            other_headers = self._create_profile(
                client, slug="other", email="other@example.com"
            )

            anonymous = client.post(
                "/api/users/owner/albums",
                json={"artist": "Artist", "name": "Album"},
            )
            cross_account = client.post(
                "/api/users/owner/albums",
                json={"artist": "Artist", "name": "Album"},
                headers=other_headers,
            )
            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={},
            ):
                created = client.post(
                    "/api/users/owner/albums",
                    json={"artist": "Artist", "name": "Album"},
                    headers=owner_headers,
                )
            album_id = created.json()["id"]
            anonymous_delete = client.delete(f"/api/users/owner/albums/{album_id}")
            cross_account_delete = client.delete(
                f"/api/users/owner/albums/{album_id}", headers=other_headers
            )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(cross_account.status_code, 403)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(anonymous_delete.status_code, 401)
        self.assertEqual(cross_account_delete.status_code, 403)

    def test_import_and_spotify_owner_operations_reject_public_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            self._create_profile(client, slug="owner", email="owner@example.com")

            import_preview = client.post(
                "/api/users/owner/imports/preview",
                json={"source": "lastfm", "lastfm_username": "owner"},
            )
            import_history = client.get("/api/users/owner/imports")
            upload = client.post(
                "/api/users/owner/imports/spotify/upload",
                files={"file": ("history.zip", b"not authorized", "application/zip")},
            )
            spotify_connect = client.post("/api/users/owner/spotify/connect")
            spotify_status = client.get("/api/users/owner/spotify/status")
            spotify_sync = client.post("/api/users/owner/spotify/sync")
            spotify_disconnect = client.delete("/api/users/owner/spotify")
            export_profile = client.get("/api/users/owner/export")
            legacy_delete = client.delete("/api/albums/1")

        for response in (
            import_preview,
            import_history,
            upload,
            spotify_connect,
            spotify_status,
            spotify_sync,
            spotify_disconnect,
            export_profile,
            legacy_delete,
        ):
            self.assertEqual(response.status_code, 401)
        self.assertFalse((Path(temp_dir) / "import_uploads").exists())
