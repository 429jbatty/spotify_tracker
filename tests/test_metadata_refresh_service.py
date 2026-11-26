import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, text

import metadata_refresh_service as refresh
import utils
from backend.app.album_identity import normalized_artist_title_identity
from backend.app.database.models import Album
from backend.app.job_database import job_session


def state_with_album():
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "most_recently_listened": [],
        "completed_albums": {
            "Artist - Old Title": {
                "artist": "Artist",
                "name": "Old Title",
                "release_year": 1999,
                "listen_history": ["2026-04-01T10:00:00.000Z"],
                "source": "musicbrainz",
            }
        },
    }


class MetadataRefreshServiceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        url = f"sqlite:///{Path(directory.name) / 'tracker.sqlite'}"
        env = patch.dict(os.environ, {"DATABASE_URL": url})
        env.start()
        self.addCleanup(env.stop)

    def test_refresh_album_preserves_listen_history_and_replaces_metadata(self):
        state = state_with_album()

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Old Title",
                "release_year": 2001,
                "image_url": "https://example.test/cover.jpg",
                "source": "musicbrainz",
            },
        ) as get_album_metadata:
            result = refresh.refresh_album_and_save(
                artist="Artist",
                album="Old Title",
            )

        album = utils.load_state()["completed_albums"]["Artist - Old Title"]

        get_album_metadata.assert_called_once_with(
            "Artist",
            "Old Title",
            spotify_url=None,
        )
        self.assertTrue(result.refreshed)
        self.assertEqual(album["release_year"], 2001)
        self.assertEqual(album["image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["listen_history"], ["2026-04-01T10:00:00.000Z"])

    def test_refresh_album_preserves_existing_values_when_refreshed_values_are_null(self):
        state = state_with_album()
        state["completed_albums"]["Artist - Old Title"].update(
            {
                "label": "Existing Label",
                "image_url": "https://example.test/existing.jpg",
                "remote_image_url": "https://example.test/existing.jpg",
            }
        )

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Old Title",
                "label": None,
                "image_url": None,
                "release_year": 2001,
                "source": "musicbrainz",
            },
        ):
            result = refresh.refresh_album_and_save(
                artist="Artist",
                album="Old Title",
            )

        album = utils.load_state()["completed_albums"]["Artist - Old Title"]

        self.assertEqual(result.status, "refreshed_with_warnings")
        self.assertEqual(album["label"], "Existing Label")
        self.assertEqual(album["image_url"], "https://example.test/existing.jpg")
        self.assertEqual(album["release_year"], 2001)
        self.assertNotIn("_refresh_warnings", album)

    def test_refresh_album_updates_remote_artwork_when_new_artwork_is_found(self):
        state = state_with_album()
        state["completed_albums"]["Artist - Old Title"].update(
            {
                "image_url": "/media/artwork/existing.jpg",
                "remote_image_url": "https://example.test/old.jpg",
                "local_image_path": "artwork/existing.jpg",
            }
        )

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Old Title",
                "image_url": "https://example.test/new.jpg",
                "source": "musicbrainz",
            },
        ):
            refresh.refresh_album_and_save(
                artist="Artist",
                album="Old Title",
            )

        album = utils.load_state()["completed_albums"]["Artist - Old Title"]

        self.assertEqual(album["image_url"], "/media/artwork/existing.jpg")
        self.assertEqual(album["remote_image_url"], "https://example.test/new.jpg")
        self.assertEqual(album["local_image_path"], "artwork/existing.jpg")

    def test_refresh_album_updates_key_when_canonical_metadata_changes(self):
        state = state_with_album()

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Canonical Title",
                "source": "musicbrainz",
            },
        ):
            result = refresh.refresh_album_and_save(
                key="Artist - Old Title",
            )

        state = utils.load_state()
        self.assertEqual(result.key, "Artist - Canonical Title")
        self.assertNotIn("Artist - Old Title", state["completed_albums"])
        self.assertIn("Artist - Canonical Title", state["completed_albums"])
        self.assertEqual(
            state["completed_albums"]["Artist - Canonical Title"]["listen_history"],
            ["2026-04-01T10:00:00.000Z"],
        )

    def test_refresh_all_records_failures_when_continuing(self):
        state = {
            "completed_albums": {
                "Artist - Album": {
                    "artist": "Artist",
                    "name": "Album",
                    "listen_history": ["2026-04-01T10:00:00.000Z"],
                },
                "Missing - Album": {
                    "artist": "Missing",
                    "name": "Album",
                    "listen_history": ["2026-04-02T10:00:00.000Z"],
                },
            }
        }

        def fake_metadata(artist, album, spotify_url=None):
            if artist == "Missing":
                return {}
            return {
                "artist": artist,
                "name": album,
                "source": "musicbrainz",
            }

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            side_effect=fake_metadata,
        ):
            results = refresh.refresh_all_albums_and_save()

        self.assertEqual(len(results), 2)
        self.assertEqual([result.refreshed for result in results], [True, False])
        self.assertEqual(results[1].status, "skipped_no_match")
        self.assertIn("No metadata returned", results[1].error)

    def test_refresh_all_skips_low_confidence_metadata_without_overwriting(self):
        state = state_with_album()

        utils.save_state(state)
        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Wrong Artist",
                "name": "Wrong Album",
                "release_year": 2026,
                "source": "musicbrainz",
                "_musicbrainz_match": {"confidence": 60},
            },
        ):
            results = refresh.refresh_all_albums_and_save()

        album = utils.load_state()["completed_albums"]["Artist - Old Title"]

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].refreshed)
        self.assertEqual(results[0].status, "skipped_low_confidence")
        self.assertEqual(album["artist"], "Artist")
        self.assertEqual(album["name"], "Old Title")
        self.assertEqual(album["release_year"], 1999)

    def test_refresh_album_and_save_uses_direct_sqlite_update(self):
        utils.save_state(state_with_album())

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Canonical Title",
                "release_year": 2001,
                "source": "musicbrainz",
            },
        ), patch(
            "backend.app.database.repositories.album_state.AlbumStateRepository.load",
            side_effect=AssertionError("load_state should not be called"),
        ), patch(
            "backend.app.database.repositories.album_state.AlbumStateRepository.replace",
            side_effect=AssertionError("save_state should not be called"),
        ):
            result = refresh.refresh_album_and_save(key="Artist - Old Title")

        loaded = utils.load_state()

        self.assertEqual(result.key, "Artist - Canonical Title")
        self.assertNotIn("Artist - Old Title", loaded["completed_albums"])
        self.assertEqual(
            loaded["completed_albums"]["Artist - Canonical Title"]["listen_history"],
            ["2026-04-01T10:00:00.000Z"],
        )
        self.assertEqual(
            loaded["completed_albums"]["Artist - Canonical Title"]["release_year"],
            2001,
        )

    def test_key_refresh_rejects_a_concurrent_rename_during_remote_lookup(self):
        utils.save_state(state_with_album())

        def rename_during_lookup(*_args, **_kwargs):
            with job_session(initialize=False) as other_session:
                other_session.execute(
                    text(
                        "UPDATE albums "
                        "SET album_key = :key, name = :title, normalized_identity = :identity "
                        "WHERE album_key = :original_key"
                    ),
                    {
                        "key": "Artist - Concurrent Title",
                        "title": "Concurrent Title",
                        "identity": normalized_artist_title_identity("Artist", "Concurrent Title"),
                        "original_key": "Artist - Old Title",
                    },
                )
                other_session.commit()
            return {
                "artist": "Artist", "name": "Remote Title", "release_year": 2001,
                "source": "musicbrainz",
            }

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            side_effect=rename_during_lookup,
        ):
            with self.assertRaisesRegex(KeyError, "Album key not found: Artist - Old Title"):
                refresh.refresh_album_and_save(artist="artist", album="old title")

        completed = utils.load_state()["completed_albums"]
        self.assertEqual(list(completed), ["Artist - Concurrent Title"])
        self.assertEqual(completed["Artist - Concurrent Title"]["release_year"], 1999)
        self.assertEqual(
            completed["Artist - Concurrent Title"]["listen_history"],
            ["2026-04-01T10:00:00.000Z"],
        )

    def test_key_refresh_keeps_manual_identity_updated_during_remote_lookup(self):
        state = state_with_album()
        key = "Artist - Old Title"
        state["completed_albums"][key]["_manual_input_identity"] = "original"
        utils.save_state(state)

        def update_identity_during_lookup(*_args, **_kwargs):
            with job_session(initialize=False) as other_session:
                album = other_session.scalars(select(Album).where(Album.album_key == key)).one()
                album.metadata_json = {**album.metadata_json, "_manual_input_identity": "concurrent"}
                other_session.commit()
            return {
                "artist": "Artist", "name": "Old Title", "release_year": 2001,
                "source": "musicbrainz",
            }

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            side_effect=update_identity_during_lookup,
        ):
            result = refresh.refresh_album_and_save(key=key)

        self.assertTrue(result.refreshed)
        with job_session(initialize=False) as session:
            album = session.scalars(select(Album).where(Album.album_key == key)).one()
            self.assertEqual(album.release_year, 2001)
            self.assertEqual(album.metadata_json["_manual_input_identity"], "concurrent")

    def test_refresh_all_albums_and_save_uses_direct_sqlite_updates(self):
        state = state_with_album()
        state["completed_albums"]["Second Artist - Album"] = {
            "artist": "Second Artist",
            "name": "Album",
            "listen_history": ["2026-04-02T10:00:00.000Z"],
            "source": "musicbrainz",
        }

        def fake_metadata(artist, album, spotify_url=None):
            return {
                "artist": artist,
                "name": f"{album} Refreshed",
                "source": "musicbrainz",
            }

        utils.save_state(state)

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            side_effect=fake_metadata,
        ), patch(
            "backend.app.database.repositories.album_state.AlbumStateRepository.load",
            side_effect=AssertionError("load_state should not be called"),
        ), patch(
            "backend.app.database.repositories.album_state.AlbumStateRepository.replace",
            side_effect=AssertionError("save_state should not be called"),
        ):
            results = refresh.refresh_all_albums_and_save()

        loaded = utils.load_state()

        self.assertEqual([result.refreshed for result in results], [True, True])
        self.assertIn("Artist - Old Title Refreshed", loaded["completed_albums"])
        self.assertIn("Second Artist - Album Refreshed", loaded["completed_albums"])
        self.assertEqual(
            loaded["completed_albums"]["Artist - Old Title Refreshed"][
                "listen_history"
            ],
            ["2026-04-01T10:00:00.000Z"],
        )


if __name__ == "__main__":
    unittest.main()
