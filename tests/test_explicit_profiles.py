"""Profile selection must never depend on a seeded or implicit profile."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import metadata_refresh_service
import utils
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.services import auth_service
from backend.app.job_database import job_session
from backend.app.main import create_app
from backend.app.services import spotify_tracking_service


class ExplicitProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict("os.environ", {
            "DATABASE_URL": f"sqlite:///{Path(directory.name) / 'profiles.sqlite'}",
            "DATA_DIR": directory.name,
            "MEDIA_DIR": directory.name,
        })
        env.start()
        self.addCleanup(env.stop)

    def test_empty_startup_and_repeated_listing_never_create_profiles(self):
        for _ in range(2):
            with TestClient(create_app()) as client:
                for _ in range(2):
                    self.assertEqual(client.get("/api/users").json(), [])
                self.assertEqual(client.get("/api/album-state").status_code, 422)
                self.assertEqual(client.post("/api/albums", json={}).status_code, 422)
                self.assertEqual(client.get("/api/album-state?user_slug=missing").status_code, 404)
                self.assertEqual(client.get("/api/users").json(), [])

    def test_helpers_require_existing_profile_and_never_create_missing_one(self):
        with job_session() as session:
            UserRepository(session).create_user(slug="listener", display_name="Listener")
        state = utils.load_state("listener")
        utils.save_state(state, "listener")
        with self.assertRaises(KeyError):
            utils.load_state("missing")
        with self.assertRaises(KeyError):
            utils.save_state(state, "missing")
        with patch("metadata_refresh_service.refresh_album_record") as remote:
            with self.assertRaises(KeyError):
                metadata_refresh_service.refresh_all_albums_and_save("missing")
            remote.assert_not_called()
        with job_session() as session:
            self.assertEqual([u.slug for u in UserRepository(session).list_users()], ["listener"])

    def test_tracking_command_requires_slug_and_passes_explicit_selection(self):
        from backend.app.jobs import track_user
        with patch("sys.argv", ["track_user"]), self.assertRaises(SystemExit) as error:
            track_user.main()
        self.assertEqual(error.exception.code, 2)
        with patch("sys.argv", ["track_user", "--user-slug", "listener"]), patch.object(
            track_user, "run_tracking_for_user"
        ) as run, patch.object(track_user, "configure_logging"):
            track_user.main()
        run.assert_called_once_with("listener")

    def test_all_profile_worker_handles_empty_database(self):
        with patch.object(spotify_tracking_service, "run_tracking_for_user") as run:
            self.assertEqual(spotify_tracking_service.run_tracking_for_all_users(), {})
            run.assert_not_called()
        with job_session() as session:
            self.assertEqual(UserRepository(session).list_users(), [])

    def test_maintenance_commands_require_profile_before_opening_database(self):
        from one_time_scripts import _dedupe_albums, _refresh_metadata
        for module in (_dedupe_albums, _refresh_metadata):
            with self.subTest(module=module.__name__), patch("sys.argv", [module.__name__]):
                with self.assertRaises(SystemExit) as error:
                    module.main()
                self.assertEqual(error.exception.code, 2)

    def test_legacy_adapter_selects_and_authorizes_an_ordinary_profile(self):
        with TestClient(create_app()) as client:
            with client.app.state.session_factory() as session:
                users = UserRepository(session)
                users.create_user(slug="jacob", display_name="Jacob")
                account = auth_service.create_account(
                    session, email="owner@example.test", password="fixture-password",
                )
                owner = users.create_user(
                    slug="listener", display_name="Listener", owner_account_id=account.id,
                )
                token = auth_service.create_session(session, account=account)
                record = AlbumLibrary(session, owner).add_album({
                    "artist": "Artist", "name": "Album", "source": "manual",
                }, listen_date="2026-01-01")
                album_id = record.record["id"]
            path = f"/api/albums/{album_id}/your-tags?user_slug=listener"
            self.assertEqual(client.put(path, json={"your_tags": []}).status_code, 401)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.assertEqual(client.put(path, json={"your_tags": ["atmospheric"]}).status_code, 200)
            denied = client.put(
                f"/api/albums/{album_id}/your-tags?user_slug=jacob", json={"your_tags": []},
            )
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(client.get("/api/album-state?user_slug=jacob").json()["completed_albums"], {})
            selected = client.get("/api/album-state?user_slug=listener").json()
            self.assertEqual(selected["completed_albums"]["Artist - Album"]["your_tags"], ["atmospheric"])

    def test_maintenance_refreshes_only_selected_library(self):
        from one_time_scripts import _dedupe_albums
        with job_session() as session:
            users = UserRepository(session)
            selected = users.create_user(slug="selected", display_name="Selected")
            other = users.create_user(slug="other", display_name="Other")
            AlbumLibrary(session, selected).add_album({
                "artist": "Artist", "name": "Selected", "source": "manual",
            }, listen_date="2026-01-01")
            foreign = AlbumLibrary(session, other).add_album({
                "artist": "Artist", "name": "Other", "source": "manual",
            }, listen_date="2026-01-02")
            with patch("metadata_refresh_service.refresh_album_record") as remote:
                actions = _dedupe_albums.refresh_candidates(AlbumLibrary(session, selected), [foreign.record["id"]])
                self.assertIn("skipped", actions[0])
                remote.assert_not_called()
        with patch("metadata_refresh_service.refresh_album_record") as remote:
            with self.assertRaises(KeyError):
                metadata_refresh_service.refresh_album_and_save(user_slug="selected", key="Artist - Other")
            remote.assert_not_called()
        with patch("metadata_refresh_service._refresh_catalog_album") as refresh:
            metadata_refresh_service.refresh_all_albums_and_save("selected")
            self.assertEqual(refresh.call_count, 1)
            self.assertEqual(refresh.call_args.kwargs["key"], "Artist - Selected")
