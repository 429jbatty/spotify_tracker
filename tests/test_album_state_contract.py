import unittest

from backend.app.schemas import AlbumState


def sample_album_state():
    return {
        "last_checked": "2026-04-18T16:14:25.872Z",
        "albums_in_progress": {
            "spotify-album-id": {
                "album_name": "Album In Progress",
                "artist": "Artist",
                "total_tracks": 10,
                "played_tracks": ["track-1", "track-2"],
                "first_played": "2026-04-18T15:00:00.000Z",
                "last_played": "2026-04-18T15:08:00.000Z",
                "completion_logged": False,
            }
        },
        "completed_albums": {
            "Artist - Finished Album": {
                "artist": "Artist",
                "name": "Finished Album",
                "artist_mbid": "artist-mbid",
                "release_group_mbid": "release-group-mbid",
                "release_mbid": "release-mbid",
                "label": "Label",
                "release_year": 2026,
                "release_month": 4,
                "release_day": 18,
                "tracklist": [
                    {
                        "position": "1",
                        "title": "Opening Track",
                        "credits": [["Producer", "producer", ""]],
                        "recording_mbid": "recording-mbid",
                    }
                ],
                "genres": ["rock"],
                "tags": ["indie"],
                "image_url": "https://example.test/cover.jpg",
                "source": "musicbrainz",
                "entry_source": "spotify_sync",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Finished Album"],
    }


class AlbumStateContractTests(unittest.TestCase):
    def test_album_state_requires_current_top_level_fields(self):
        AlbumState.model_validate(sample_album_state())

        self.assertEqual(
            set(AlbumState.model_fields),
            {
                "last_checked",
                "albums_in_progress",
                "completed_albums",
                "most_recently_listened",
            },
        )

    def test_completed_album_preserves_frontend_fields(self):
        state = AlbumState.model_validate(sample_album_state())
        album = state.completed_albums["Artist - Finished Album"]

        self.assertEqual(album.artist, "Artist")
        self.assertEqual(album.name, "Finished Album")
        self.assertEqual(album.listen_history, ["2026-04-18T15:45:00.000Z"])
        self.assertEqual(album.release_year, 2026)
        self.assertEqual(album.release_month, 4)
        self.assertEqual(album.release_day, 18)
        self.assertEqual(album.tracklist[0].title, "Opening Track")
        self.assertEqual(album.tags, ["indie"])
        self.assertEqual(album.genres, ["rock"])
        self.assertEqual(album.your_tags, [])
        self.assertIsNone(album.rating)
        self.assertIsNone(album.notes)
        self.assertEqual(album.image_url, "https://example.test/cover.jpg")
        self.assertEqual(album.source, "musicbrainz")
        self.assertEqual(album.entry_source, "spotify_sync")


if __name__ == "__main__":
    unittest.main()
