import unittest
from unittest.mock import patch

import album_metadata_service as metadata


def release_group():
    return {
        "id": "release-group-1",
        "title": "Test Album",
        "primary-type": "Album",
        "first-release-date": "2020-05-12",
        "artist-credit": [
            {
                "name": "Test Artist",
                "artist": {"id": "artist-1"},
            }
        ],
        "tag-list": [{"name": "indie rock"}, {"name": "dream pop"}],
    }


def full_release():
    return {
        "id": "release-1",
        "label-info-list": [{"label": {"name": "Test Label"}}],
        "medium-list": [
            {
                "track-list": [
                    {
                        "position": "1",
                        "recording": {
                            "id": "recording-1",
                            "title": "Opening Track",
                            "artist-relation-list": [
                                {
                                    "type": "producer",
                                    "artist": {"name": "Producer One"},
                                    "attributes": [{"attribute": "co"}],
                                }
                            ],
                        },
                    },
                    {
                        "position": "2",
                        "recording": {
                            "id": "recording-2",
                            "title": "Second Track",
                        },
                    },
                ]
            }
        ],
    }


class AlbumMetadataServiceTests(unittest.TestCase):
    def test_get_album_metadata_builds_album_record_from_musicbrainz_search(self):
        release_summaries = [
            {
                "id": "other-release",
                "title": "Test Album",
                "status": "Bootleg",
                "date": "2019-01-01",
                "medium-list": [{"format": "Digital Media"}],
            },
            {
                "id": "release-1",
                "title": "Test Album",
                "status": "Official",
                "date": "2020-05-12",
                "country": "US",
                "medium-list": [{"format": "Digital Media"}],
            },
        ]

        with (
            patch(
                "album_metadata_service.mb.search_release_groups",
                return_value=[release_group()],
            ) as search_release_groups,
            patch(
                "album_metadata_service.mb.get_releases_for_group",
                return_value=release_summaries,
            ) as get_releases_for_group,
            patch(
                "album_metadata_service.mb.get_release_by_id",
                return_value=full_release(),
            ) as get_release_by_id,
            patch(
                "album_metadata_service.mb.get_cover_art_url",
                return_value="https://example.test/cover.jpg",
            ),
        ):
            album = metadata.get_album_metadata("Test Artist", "Test Album")

        search_release_groups.assert_called_once_with("Test Artist", "Test Album")
        get_releases_for_group.assert_called_once_with("release-group-1")
        get_release_by_id.assert_called_once_with("release-1")

        self.assertEqual(album["artist"], "Test Artist")
        self.assertEqual(album["artist_mbid"], "artist-1")
        self.assertEqual(album["name"], "Test Album")
        self.assertEqual(album["release_group_mbid"], "release-group-1")
        self.assertEqual(album["label"], "Test Label")
        self.assertEqual(album["release_year"], 2020)
        self.assertEqual(album["release_month"], 5)
        self.assertEqual(album["release_day"], 12)
        self.assertEqual(album["tags"], ["indie rock", "dream pop"])
        self.assertEqual(album["image_url"], "https://example.test/cover.jpg")
        self.assertEqual(album["source"], "musicbrainz")
        self.assertEqual(
            album["tracklist"],
            [
                {
                    "position": "1",
                    "title": "Opening Track",
                    "credits": [("Producer One", "producer", "co")],
                    "recording_mbid": "recording-1",
                },
                {
                    "position": "2",
                    "title": "Second Track",
                    "credits": {},
                    "recording_mbid": "recording-2",
                },
            ],
        )

    def test_get_album_metadata_uses_spotify_url_match_when_available(self):
        spotify_release = {
            "id": "release-1",
            "release-group": release_group(),
        }

        with (
            patch(
                "album_metadata_service.mb.search_release_by_spotify_url",
                return_value=spotify_release,
            ) as search_release_by_spotify_url,
            patch(
                "album_metadata_service.mb.search_release_groups",
            ) as search_release_groups,
            patch(
                "album_metadata_service.mb.get_release_by_id",
                return_value=full_release(),
            ) as get_release_by_id,
            patch(
                "album_metadata_service.mb.get_cover_art_url",
                return_value="https://example.test/cover.jpg",
            ),
        ):
            album = metadata.get_album_metadata(
                "Test Artist",
                "Test Album",
                spotify_url="https://open.spotify.com/album/test",
            )

        search_release_by_spotify_url.assert_called_once_with(
            "https://open.spotify.com/album/test"
        )
        search_release_groups.assert_not_called()
        get_release_by_id.assert_called_once_with("release-1")
        self.assertEqual(album["release_group_mbid"], "release-group-1")

    def test_get_album_metadata_returns_empty_dict_when_no_match(self):
        with patch(
            "album_metadata_service.mb.search_release_groups",
            return_value=[],
        ):
            album = metadata.get_album_metadata("Missing Artist", "Missing Album")

        self.assertEqual(album, {})


if __name__ == "__main__":
    unittest.main()
