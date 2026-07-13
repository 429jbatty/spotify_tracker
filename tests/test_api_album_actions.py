import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services import auth_service


def sample_album_state():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Old Title": {
                "artist": "Artist",
                "name": "Old Title",
                "release_year": 1999,
                "source": "musicbrainz",
                "listen_history": ["2026-04-01T10:00:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Old Title"],
    }


class ApiAlbumActionTests(unittest.TestCase):
    def _client(self, temp_dir, state=None):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with session_factory() as session:
            repository = SqliteStateRepository(session)
            repository.save_album_state(state or sample_album_state())
            album = next(iter(repository.load_album_state()["completed_albums"].values()))
            account = auth_service.create_account(
                session,
                email="owner@example.com",
                password="correct-horse-battery-staple",
            )
            repository.user.owner_account_id = account.id
            token = auth_service.create_session(session, account=account)
            session.commit()

        env = {
            "DATABASE_URL": database_url,
            "MEDIA_DIR": temp_dir,
        }
        patcher = patch.dict("os.environ", env)
        patcher.start()
        self.addCleanup(patcher.stop)
        client = TestClient(create_app())
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client, album["id"], database_url

    def test_refresh_one_album_updates_metadata_and_preserves_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            with patch(
                "backend.app.routers.albums.metadata_refresh_service.refresh_album_record",
                return_value={
                    "artist": "Artist",
                    "name": "Canonical Title",
                    "release_year": 2001,
                    "source": "musicbrainz",
                },
            ):
                response = client.post(f"/api/albums/{album_id}/refresh-metadata")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["name"], "Canonical Title")
            self.assertEqual(payload["release_year"], 2001)
            self.assertEqual(payload["listen_history"], ["2026-04-01T10:00:00.000Z"])

    def test_failed_refresh_does_not_partially_update_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            with patch(
                "backend.app.routers.albums.metadata_refresh_service.refresh_album_record",
                side_effect=LookupError("No metadata returned."),
            ):
                response = client.post(f"/api/albums/{album_id}/refresh-metadata")

            state = client.get("/api/album-state").json()
            album = state["completed_albums"]["Artist - Old Title"]

        self.assertEqual(response.status_code, 502)
        self.assertEqual(album["release_year"], 1999)
        self.assertEqual(album["listen_history"], ["2026-04-01T10:00:00.000Z"])

    def test_manual_album_creation_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            response = client.post("/api/albums", json={"artist": "Artist"})

        self.assertEqual(response.status_code, 422)

    def test_manual_album_creation_adds_album_and_initial_listen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={},
            ):
                response = client.post(
                    "/api/albums",
                    json={
                        "artist": "New Artist",
                        "name": "New Album",
                        "listen_date": "2026-04-02T10:00:00.000Z",
                    },
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["artist"], "New Artist")
        self.assertEqual(payload["name"], "New Album")
        self.assertEqual(payload["listen_history"], ["2026-04-02T10:00:00.000Z"])
        self.assertEqual(payload["source"], "manual")
        self.assertEqual(payload["entry_source"], "manual")

    def test_manual_album_creation_without_listen_date_creates_album_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={},
            ):
                response = client.post(
                    "/api/albums",
                    json={"artist": "New Artist", "name": "No Listen Album"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["artist"], "New Artist")
        self.assertEqual(payload["name"], "No Listen Album")
        self.assertEqual(payload["listen_history"], [])

    def test_manual_album_creation_uses_high_confidence_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={
                    "artist": "Canonical Artist",
                    "name": "Canonical Album",
                    "release_year": 2026,
                    "release_group_mbid": "release-group-1",
                    "source": "musicbrainz",
                    "_musicbrainz_match": {"confidence": 91},
                },
            ):
                response = client.post(
                    "/api/albums",
                    json={"artist": "Input Artist", "name": "Input Album"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["artist"], "Canonical Artist")
        self.assertEqual(payload["name"], "Canonical Album")
        self.assertEqual(payload["release_year"], 2026)
        self.assertEqual(payload["release_group_mbid"], "release-group-1")
        self.assertEqual(payload["source"], "musicbrainz")
        self.assertEqual(payload["entry_source"], "manual")

    def test_manual_album_creation_falls_back_for_low_confidence_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={
                    "artist": "Wrong Artist",
                    "name": "Wrong Album",
                    "source": "musicbrainz",
                    "_musicbrainz_match": {"confidence": 60},
                },
            ):
                response = client.post(
                    "/api/albums",
                    json={"artist": "Input Artist", "name": "Input Album"},
                )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["artist"], "Input Artist")
        self.assertEqual(payload["name"], "Input Album")
        self.assertEqual(payload["source"], "manual")
        self.assertEqual(payload["entry_source"], "manual")

    def test_duplicate_album_creation_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            with patch(
                "backend.app.services.manual_album_service.album_metadata_service.get_album_metadata",
                return_value={},
            ):
                response = client.post(
                    "/api/albums",
                    json={
                        "artist": "Artist",
                        "name": "Old Title",
                        "listen_date": "2026-04-02T10:00:00.000Z",
                    },
                )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Album already exists", response.json()["detail"])

    def test_metadata_edit_updates_only_supplied_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.patch(
                f"/api/albums/{album_id}",
                json={"label": "New Label"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["artist"], "Artist")
        self.assertEqual(payload["name"], "Old Title")
        self.assertEqual(payload["release_year"], 1999)
        self.assertEqual(payload["label"], "New Label")
        self.assertEqual(payload["listen_history"], ["2026-04-01T10:00:00.000Z"])

    def test_metadata_edit_duplicate_key_returns_merge_candidate(self):
        state = sample_album_state()
        state["completed_albums"] = {
            "The Jimi Hendrix Experience - Electric Ladyland": {
                "artist": "The Jimi Hendrix Experience",
                "name": "Electric Ladyland",
                "source": "musicbrainz",
                "listen_history": ["2026-03-01T10:00:00.000Z"],
            },
            "Jimi Hendrix - Electric Ladyland": {
                "artist": "Jimi Hendrix",
                "name": "Electric Ladyland",
                "source": "unknown",
                "listen_history": ["2026-04-18T23:36:49.796Z"],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir, state=state)
            initial_state = client.get("/api/album-state").json()
            duplicate_id = initial_state["completed_albums"][
                "Jimi Hendrix - Electric Ladyland"
            ]["id"]

            response = client.patch(
                f"/api/albums/{duplicate_id}",
                json={"artist": "The Jimi Hendrix Experience"},
            )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "duplicate_album_key")
        self.assertEqual(
            detail["target_album"]["album_key"],
            "The Jimi Hendrix Experience - Electric Ladyland",
        )

    def test_merge_album_moves_listens_and_deletes_source(self):
        state = sample_album_state()
        state["completed_albums"] = {
            "The Jimi Hendrix Experience - Electric Ladyland": {
                "artist": "The Jimi Hendrix Experience",
                "name": "Electric Ladyland",
                "source": "musicbrainz",
                "listen_history": ["2026-03-01T10:00:00.000Z"],
            },
            "Jimi Hendrix - Electric Ladyland": {
                "artist": "Jimi Hendrix",
                "name": "Electric Ladyland",
                "source": "unknown",
                "listen_history": ["2026-04-18T23:36:49.796Z"],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir, state=state)
            initial_state = client.get("/api/album-state").json()
            duplicate_id = initial_state["completed_albums"][
                "Jimi Hendrix - Electric Ladyland"
            ]["id"]
            canonical_id = initial_state["completed_albums"][
                "The Jimi Hendrix Experience - Electric Ladyland"
            ]["id"]

            response = client.post(
                f"/api/albums/{duplicate_id}/merge",
                json={"target_album_id": canonical_id},
            )
            refreshed_state = client.get("/api/album-state").json()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], canonical_id)
        self.assertEqual(
            payload["listen_history"],
            ["2026-03-01T10:00:00.000Z", "2026-04-18T23:36:49.796Z"],
        )
        self.assertNotIn(
            "Jimi Hendrix - Electric Ladyland",
            refreshed_state["completed_albums"],
        )

    def test_add_album_listen_appends_without_duplicate_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.post(
                f"/api/albums/{album_id}/listens",
                json={"listened_at": "2026-04-02T10:00:00.000Z"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["listen_history"],
            ["2026-04-01T10:00:00.000Z", "2026-04-02T10:00:00.000Z"],
        )

    def test_update_album_user_tags_replaces_tag_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.put(
                f"/api/albums/{album_id}/your-tags",
                json={"your_tags": ["atmospheric", "cohesive"]},
            )

            refreshed_state = client.get("/api/album-state").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["your_tags"], ["atmospheric", "cohesive"])
        self.assertEqual(
            refreshed_state["completed_albums"]["Artist - Old Title"]["your_tags"],
            ["atmospheric", "cohesive"],
        )

    def test_update_album_user_tags_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.put(
                f"/api/albums/{album_id}/your-tags",
                json={"your_tags": ["made-up-tag"]},
            )

        self.assertEqual(response.status_code, 422)

    def test_update_album_user_feedback_replaces_rating_and_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.put(
                f"/api/albums/{album_id}/your-feedback",
                json={"rating": 7, "notes": "Strong opener, weaker middle."},
            )

            refreshed_state = client.get("/api/album-state").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rating"], 7)
        self.assertEqual(response.json()["notes"], "Strong opener, weaker middle.")
        self.assertEqual(
            refreshed_state["completed_albums"]["Artist - Old Title"]["rating"],
            7,
        )
        self.assertEqual(
            refreshed_state["completed_albums"]["Artist - Old Title"]["notes"],
            "Strong opener, weaker middle.",
        )

    def test_delete_album_listen_removes_only_that_listen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)
            client.post(
                f"/api/albums/{album_id}/listens",
                json={"listened_at": "2026-04-02T10:00:00.000Z"},
            )

            response = client.request(
                "DELETE",
                f"/api/albums/{album_id}/listens",
                json={"listened_at": "2026-04-01T10:00:00.000Z"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["listen_history"], ["2026-04-02T10:00:00.000Z"])

    def test_delete_missing_album_listen_returns_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.request(
                "DELETE",
                f"/api/albums/{album_id}/listens",
                json={"listened_at": "2026-04-03T10:00:00.000Z"},
            )

        self.assertEqual(response.status_code, 404)

    def test_refresh_duplicate_album_merges_listens_and_deletes_source(self):
        state = sample_album_state()
        state["completed_albums"] = {
            "The Jimi Hendrix Experience - Electric Ladyland": {
                "artist": "The Jimi Hendrix Experience",
                "name": "Electric Ladyland",
                "release_group_mbid": "canonical-release-group",
                "source": "musicbrainz",
                "listen_history": ["2026-03-01T10:00:00.000Z"],
            },
            "Jimi Hendrix - Electric Ladyland": {
                "artist": "Jimi Hendrix",
                "name": "Electric Ladyland",
                "source": "unknown",
                "listen_history": ["2026-04-18T23:36:49.796Z"],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir, state=state)
            initial_state = client.get("/api/album-state").json()
            duplicate_id = initial_state["completed_albums"][
                "Jimi Hendrix - Electric Ladyland"
            ]["id"]
            canonical_id = initial_state["completed_albums"][
                "The Jimi Hendrix Experience - Electric Ladyland"
            ]["id"]

            with patch(
                "backend.app.routers.albums.metadata_refresh_service.refresh_album_record",
                return_value={
                    "artist": "The Jimi Hendrix Experience",
                    "name": "Electric Ladyland",
                    "release_group_mbid": "canonical-release-group",
                    "release_year": 1968,
                    "source": "musicbrainz",
                },
            ):
                response = client.post(f"/api/albums/{duplicate_id}/refresh-metadata")

            refreshed_state = client.get("/api/album-state").json()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], canonical_id)
        self.assertEqual(payload["artist"], "The Jimi Hendrix Experience")
        self.assertEqual(payload["name"], "Electric Ladyland")
        self.assertEqual(payload["release_year"], 1968)
        self.assertEqual(
            payload["listen_history"],
            ["2026-03-01T10:00:00.000Z", "2026-04-18T23:36:49.796Z"],
        )
        self.assertIn(
            "The Jimi Hendrix Experience - Electric Ladyland",
            refreshed_state["completed_albums"],
        )
        self.assertNotIn(
            "Jimi Hendrix - Electric Ladyland",
            refreshed_state["completed_albums"],
        )

    def test_delete_album_removes_album_and_listens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, album_id, _ = self._client(temp_dir)

            response = client.delete(f"/api/albums/{album_id}")
            refreshed_state = client.get("/api/album-state").json()

        self.assertEqual(response.status_code, 204)
        self.assertEqual(refreshed_state["completed_albums"], {})
        self.assertEqual(refreshed_state["most_recently_listened"], [])

    def test_delete_missing_album_returns_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _, _ = self._client(temp_dir)

            response = client.delete("/api/albums/999999")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
