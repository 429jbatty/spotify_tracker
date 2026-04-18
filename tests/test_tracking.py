import unittest
from unittest.mock import patch

import tracking


class FakeSpotify:
    def __init__(self):
        self.fetches = []

    def fetch_album_metadata(self, album_id):
        self.fetches.append(album_id)
        return {"album_type": "album", "total_tracks": 2}


class TrackingTests(unittest.TestCase):
    def test_update_album_progress_processes_tracks_chronologically(self):
        state = {"albums_in_progress": {}, "completed_albums": {}}
        tracks = [
            {
                "album_id": "album-1",
                "album_name": "Album",
                "artist": "Artist",
                "track_spid": "track-2",
                "played_at": "2026-04-17T10:05:00.000Z",
            },
            {
                "album_id": "album-1",
                "album_name": "Album",
                "artist": "Artist",
                "track_spid": "track-1",
                "played_at": "2026-04-17T10:00:00.000Z",
            },
        ]

        updated = tracking.update_album_progress(state, FakeSpotify(), tracks)
        album = updated["albums_in_progress"]["album-1"]

        self.assertEqual(album["first_played"], "2026-04-17T10:00:00.000Z")
        self.assertEqual(album["last_played"], "2026-04-17T10:05:00.000Z")

    def test_logged_album_progress_restarts_for_subsequent_listen(self):
        state = {
            "albums_in_progress": {
                "album-1": {
                    "album_name": "Album",
                    "artist": "Artist",
                    "total_tracks": 2,
                    "played_tracks": ["old-track-1", "old-track-2"],
                    "first_played": "2026-04-17T09:00:00.000Z",
                    "last_played": "2026-04-17T09:05:00.000Z",
                    "completion_logged": True,
                }
            },
            "completed_albums": {},
        }
        tracks = [
            {
                "album_id": "album-1",
                "album_name": "Album",
                "artist": "Artist",
                "track_spid": "new-track-1",
                "played_at": "2026-04-17T10:00:00.000Z",
            }
        ]

        updated = tracking.update_album_progress(state, FakeSpotify(), tracks)
        album = updated["albums_in_progress"]["album-1"]

        self.assertEqual(album["played_tracks"], ["new-track-1"])
        self.assertNotIn("completion_logged", album)

    def test_subsequent_listen_appends_without_refetching_metadata(self):
        state = {
            "albums_in_progress": {
                "album-1": {
                    "album_name": "Album",
                    "artist": "Artist",
                    "total_tracks": 2,
                    "played_tracks": ["track-1", "track-2"],
                    "first_played": "2026-04-17T10:00:00.000Z",
                    "last_played": "2026-04-17T10:05:00.000Z",
                }
            },
            "completed_albums": {
                "Artist - Album": {
                    "artist": "Artist",
                    "name": "Album",
                    "listen_history": ["2026-04-16T10:05:00.000Z"],
                    "source": "musicbrainz",
                }
            },
        }

        with patch("tracking.meta.get_album_metadata") as get_album_metadata:
            entry = tracking.log_completed_album(state, "album-1")

        self.assertEqual(
            entry["Artist - Album"]["listen_history"],
            ["2026-04-16T10:05:00.000Z", "2026-04-17T10:05:00.000Z"],
        )
        get_album_metadata.assert_not_called()


if __name__ == "__main__":
    unittest.main()
