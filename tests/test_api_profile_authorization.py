import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.models import Album, AlbumCreditFact


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

    def _create_album(self, client, *, slug, headers, artist, name):
        with patch(
            "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
            return_value={},
        ):
            response = client.post(
                f"/api/users/{slug}/albums",
                json={"artist": artist, "name": name},
                headers=headers,
            )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def _add_credit_fact(self, temp_dir, album_id, *, person_key):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        session_factory = sessionmaker(bind=create_schema(database_url))
        with session_factory() as session:
            session.add(
                AlbumCreditFact(
                    album_id=album_id,
                    person_key=person_key,
                    person_name="Test Producer",
                    person_mbid=None,
                    identity_resolution="name",
                    ingestion_version="test",
                    raw_role="producer",
                    role_bucket="producer",
                    source_scope="release_group",
                    recording_mbid=None,
                    track_count=1,
                    album_track_count=1,
                    track_share=1.0,
                    quality_flags_json=[],
                    created_at="2026-07-17T00:00:00Z",
                    updated_at="2026-07-17T00:00:00Z",
                )
            )
            session.commit()

    def _album_and_fact_exist(self, temp_dir, album_id):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        session_factory = sessionmaker(bind=create_schema(database_url))
        with session_factory() as session:
            return (
                session.get(Album, album_id) is not None,
                session.scalar(
                    select(AlbumCreditFact.id).where(
                        AlbumCreditFact.album_id == album_id
                    )
                )
                is not None,
            )

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

    def test_owner_cannot_mutate_albums_outside_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            alice_headers = self._create_profile(
                client, slug="alice", email="alice@example.com"
            )
            bob_headers = self._create_profile(
                client, slug="bob", email="bob@example.com"
            )
            alice_album_id = self._create_album(
                client,
                slug="alice",
                headers=alice_headers,
                artist="Alice Artist",
                name="Alice Album",
            )
            bob_album_id = self._create_album(
                client,
                slug="bob",
                headers=bob_headers,
                artist="Bob Artist",
                name="Bob Album",
            )

            with patch(
                "backend.app.routers.users.metadata_refresh_service.refresh_album_record"
            ) as refresh:
                refresh_response = client.post(
                    f"/api/users/alice/albums/{bob_album_id}/refresh-metadata",
                    headers=alice_headers,
                )
            update_response = client.patch(
                f"/api/users/alice/albums/{bob_album_id}",
                json={"name": "Changed by Alice"},
                headers=alice_headers,
            )
            merge_response = client.post(
                f"/api/users/alice/albums/{alice_album_id}/merge",
                json={"target_album_id": bob_album_id},
                headers=alice_headers,
            )
            delete_response = client.delete(
                f"/api/users/alice/albums/{bob_album_id}", headers=alice_headers
            )
            bob_state = client.get("/api/users/bob/album-state").json()

        refresh.assert_not_called()
        for response in (
            refresh_response,
            update_response,
            merge_response,
            delete_response,
        ):
            self.assertEqual(response.status_code, 404)
        self.assertIn("Bob Artist - Bob Album", bob_state["completed_albums"])

    def test_delete_and_merge_only_remove_current_profiles_membership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            alice_headers = self._create_profile(
                client, slug="alice", email="alice@example.com"
            )
            bob_headers = self._create_profile(
                client, slug="bob", email="bob@example.com"
            )

            shared_id = self._create_album(
                client,
                slug="alice",
                headers=alice_headers,
                artist="Shared Artist",
                name="Shared Album",
            )
            self._create_album(
                client,
                slug="bob",
                headers=bob_headers,
                artist="Shared Artist",
                name="Shared Album",
            )
            source_id = self._create_album(
                client,
                slug="alice",
                headers=alice_headers,
                artist="Duplicate Artist",
                name="Source Album",
            )
            self._create_album(
                client,
                slug="bob",
                headers=bob_headers,
                artist="Duplicate Artist",
                name="Source Album",
            )
            target_id = self._create_album(
                client,
                slug="alice",
                headers=alice_headers,
                artist="Duplicate Artist",
                name="Target Album",
            )

            delete_response = client.delete(
                f"/api/users/alice/albums/{shared_id}", headers=alice_headers
            )
            merge_response = client.post(
                f"/api/users/alice/albums/{source_id}/merge",
                json={"target_album_id": target_id},
                headers=alice_headers,
            )
            alice_state = client.get("/api/users/alice/album-state").json()
            bob_state = client.get("/api/users/bob/album-state").json()

        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(merge_response.status_code, 200)
        self.assertNotIn("Shared Artist - Shared Album", alice_state["completed_albums"])
        self.assertIn("Shared Artist - Shared Album", bob_state["completed_albums"])
        self.assertNotIn(
            "Duplicate Artist - Source Album", alice_state["completed_albums"]
        )
        self.assertIn(
            "Duplicate Artist - Source Album", bob_state["completed_albums"]
        )

    def test_delete_and_merge_remove_last_membership_with_credit_facts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            headers = self._create_profile(
                client, slug="owner", email="owner@example.com"
            )
            delete_id = self._create_album(
                client,
                slug="owner",
                headers=headers,
                artist="Delete Artist",
                name="Delete Album",
            )
            source_id = self._create_album(
                client,
                slug="owner",
                headers=headers,
                artist="Merge Artist",
                name="Source Album",
            )
            target_id = self._create_album(
                client,
                slug="owner",
                headers=headers,
                artist="Merge Artist",
                name="Target Album",
            )
            self._add_credit_fact(temp_dir, delete_id, person_key="delete-producer")
            self._add_credit_fact(temp_dir, source_id, person_key="source-producer")

            delete_response = client.delete(
                f"/api/users/owner/albums/{delete_id}", headers=headers
            )
            merge_response = client.post(
                f"/api/users/owner/albums/{source_id}/merge",
                json={"target_album_id": target_id},
                headers=headers,
            )
            deleted_state = self._album_and_fact_exist(temp_dir, delete_id)
            merged_state = self._album_and_fact_exist(temp_dir, source_id)

        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(merge_response.status_code, 200)
        self.assertEqual(deleted_state, (False, False))
        self.assertEqual(merged_state, (False, False))
