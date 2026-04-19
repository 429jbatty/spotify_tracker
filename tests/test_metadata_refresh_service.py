import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import metadata_refresh_service as refresh
import utils


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
    def test_refresh_album_preserves_listen_history_and_replaces_metadata(self):
        state = state_with_album()

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
            result = refresh.refresh_album_in_state(
                state,
                artist="Artist",
                album="Old Title",
            )

        album = state["completed_albums"]["Artist - Old Title"]

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
            result = refresh.refresh_album_in_state(
                state,
                artist="Artist",
                album="Old Title",
            )

        album = state["completed_albums"]["Artist - Old Title"]

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

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Old Title",
                "image_url": "https://example.test/new.jpg",
                "source": "musicbrainz",
            },
        ):
            refresh.refresh_album_in_state(
                state,
                artist="Artist",
                album="Old Title",
            )

        album = state["completed_albums"]["Artist - Old Title"]

        self.assertEqual(album["image_url"], "https://example.test/new.jpg")
        self.assertEqual(album["remote_image_url"], "https://example.test/new.jpg")
        self.assertEqual(album["local_image_path"], "artwork/existing.jpg")

    def test_refresh_album_updates_key_when_canonical_metadata_changes(self):
        state = state_with_album()

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            return_value={
                "artist": "Artist",
                "name": "Canonical Title",
                "source": "musicbrainz",
            },
        ):
            result = refresh.refresh_album_in_state(
                state,
                key="Artist - Old Title",
            )

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

        with patch(
            "metadata_refresh_service.metadata_service.get_album_metadata",
            side_effect=fake_metadata,
        ):
            results = refresh.refresh_all_albums_in_state(state)

        self.assertEqual(len(results), 2)
        self.assertEqual([result.refreshed for result in results], [True, False])
        self.assertEqual(results[1].status, "skipped_no_match")
        self.assertIn("No metadata returned", results[1].error)

    def test_refresh_album_and_save_uses_direct_sqlite_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            with patch.dict(
                os.environ,
                {
                    "ALBUM_STATE_BACKEND": "sqlite",
                    "DATABASE_URL": database_url,
                },
            ):
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
                    "metadata_refresh_service.utils.load_state",
                    side_effect=AssertionError("load_state should not be called"),
                ), patch(
                    "metadata_refresh_service.utils.save_state",
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

    def test_refresh_all_albums_and_save_uses_direct_sqlite_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
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

            with patch.dict(
                os.environ,
                {
                    "ALBUM_STATE_BACKEND": "sqlite",
                    "DATABASE_URL": database_url,
                },
            ):
                utils.save_state(state)

                with patch(
                    "metadata_refresh_service.metadata_service.get_album_metadata",
                    side_effect=fake_metadata,
                ), patch(
                    "metadata_refresh_service.utils.load_state",
                    side_effect=AssertionError("load_state should not be called"),
                ), patch(
                    "metadata_refresh_service.utils.save_state",
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
