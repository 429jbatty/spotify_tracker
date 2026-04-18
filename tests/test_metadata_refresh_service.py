import unittest
from unittest.mock import patch

import metadata_refresh_service as refresh


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
        self.assertIn("No metadata returned", results[1].error)


if __name__ == "__main__":
    unittest.main()
