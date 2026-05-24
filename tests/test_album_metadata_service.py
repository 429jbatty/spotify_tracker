import os
import unittest
from unittest.mock import patch

import musicbrainzngs

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
        "genre-list": [{"name": "folk"}],
    }


def full_release():
    return {
        "id": "release-1",
        "title": "Test Album",
        "status": "Official",
        "date": "2020-05-12",
        "country": "US",
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
                "album_metadata_service.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
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
        self.assertEqual(album["primary_type"], "Album")
        self.assertEqual(album["secondary_types"], [])
        self.assertEqual(album["release_group_mbid"], "release-group-1")
        self.assertEqual(album["release_mbid"], "release-1")
        self.assertEqual(album["label"], "Test Label")
        self.assertEqual(album["release_year"], 2020)
        self.assertEqual(album["release_month"], 5)
        self.assertEqual(album["release_day"], 12)
        self.assertEqual(album["tags"], ["indie rock", "dream pop"])
        self.assertEqual(album["genres"], ["folk"])
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
                "album_metadata_service.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
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

    def test_cover_art_network_error_does_not_prevent_metadata_refresh(self):
        release_summaries = [
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
            ),
            patch(
                "album_metadata_service.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
            patch(
                "album_metadata_service.mb.get_releases_for_group",
                return_value=release_summaries,
            ),
            patch(
                "album_metadata_service.mb.get_release_by_id",
                return_value=full_release(),
            ),
            patch(
                "album_metadata_service.mb.get_cover_art_url",
                side_effect=musicbrainzngs.NetworkError(cause=OSError("dns")),
            ),
        ):
            album = metadata.get_album_metadata("Test Artist", "Test Album")

        self.assertEqual(album["artist"], "Test Artist")
        self.assertEqual(album["name"], "Test Album")
        self.assertIsNone(album["image_url"])

    def test_choose_best_enriched_release_prefers_cover_art_and_base_track_count(self):
        enriched = [
            {
                "summary": {"id": "jp", "status": "Official"},
                "release": {
                    "id": "jp",
                    "title": "Test Album",
                    "status": "Official",
                    "country": "JP",
                    "medium-list": [{"format": "CD", "track-count": 16}],
                },
                "image_url": None,
            },
            {
                "summary": {"id": "gb-vinyl", "status": "Official"},
                "release": {
                    "id": "gb-vinyl",
                    "title": "Test Album",
                    "status": "Official",
                    "date": "1971",
                    "country": "GB",
                    "label-info-list": [{"label": {"name": "Dandelion Records"}}],
                    "medium-list": [{"format": '12" Vinyl', "track-count": 12}],
                },
                "image_url": "https://example.test/vinyl.jpg",
            },
            {
                "summary": {"id": "gb-cd", "status": "Official"},
                "release": {
                    "id": "gb-cd",
                    "title": "Test Album",
                    "status": "Official",
                    "date": "2005-11",
                    "country": "GB",
                    "label-info-list": [{"label": {"name": "Cherry Red Records"}}],
                    "medium-list": [{"format": "CD", "track-count": 12}],
                    "artist-relation-list": [
                        {"type": "producer", "artist": {"name": "Producer"}}
                    ],
                },
                "image_url": "https://example.test/cd.jpg",
            },
        ]

        chosen = metadata._choose_best_enriched_release(enriched, "Test Album")

        self.assertEqual(chosen["release"]["id"], "gb-cd")

    def test_extract_recording_credits_includes_work_level_artist_relations(self):
        recording = {
            "id": "recording-1",
            "artist-relation-list": [
                {
                    "type": "producer",
                    "artist": {"name": "Producer One"},
                    "attributes": [{"attribute": "co"}],
                }
            ],
            "work-relation-list": [
                {
                    "type": "performance",
                    "work": {
                        "artist-relation-list": [
                            {
                                "type": "composer",
                                "artist": {"name": "Composer One"},
                            }
                        ]
                    },
                }
            ],
        }

        credits = metadata._extract_recording_credits(recording)

        self.assertEqual(
            credits,
            [
                ("Producer One", "producer", "co"),
                ("Composer One", "work composer", ""),
            ],
        )


@unittest.skipUnless(
    os.environ.get("RUN_LIVE_MUSICBRAINZ_TESTS") == "1",
    "Set RUN_LIVE_MUSICBRAINZ_TESTS=1 to run live MusicBrainz tests.",
)
class LiveMusicBrainzAlbumMetadataTests(unittest.TestCase):
    def test_bridget_st_john_songs_for_the_gentle_man_has_artwork_and_tracklist(self):
        album = metadata.get_album_metadata(
            "Bridget St. John",
            "Songs for the Gentle Man",
        )

        self.assertEqual(
            album["release_group_mbid"],
            "fe939459-7a1d-3cd2-8020-b33f1649eb0e",
        )
        self.assertEqual(album["artist"], "Bridget St. John")
        self.assertEqual(album["name"], "Songs for the Gentle Man")
        self.assertEqual(album["release_year"], 1971)
        self.assertIn(album["release_mbid"], {
            "54c76f09-7d74-4c4f-bc6d-ce584cafdbc7",
            "85aae80e-16b7-4df7-852a-0521ae816afe",
        })
        self.assertTrue(album["image_url"].startswith("https://coverartarchive.org/"))
        self.assertGreaterEqual(len(album["tracklist"]), 12)


if __name__ == "__main__":
    unittest.main()
