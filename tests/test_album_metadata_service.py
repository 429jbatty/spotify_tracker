import os
import unittest
from contextlib import contextmanager
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


def release_group_for(
    release_group_id,
    title,
    artist="Test Artist",
    *,
    primary_type="Album",
    secondary_types=None,
    score=100,
    first_release_date="1970-01-01",
    disambiguation=None,
    aliases=None,
):
    group = {
        "id": release_group_id,
        "title": title,
        "primary-type": primary_type,
        "secondary-type-list": secondary_types or [],
        "first-release-date": first_release_date,
        "score": score,
        "artist-credit": [
            {
                "name": artist,
                "artist": {"id": f"{release_group_id}-artist"},
            }
        ],
    }
    if disambiguation is not None:
        group["disambiguation"] = disambiguation
    if aliases is not None:
        group["alias-list"] = [{"alias": alias} for alias in aliases]
    return group


def release_summary_for(
    release_id,
    title,
    *,
    date="1970-01-01",
    status="Official",
    country="US",
    track_count=4,
):
    return {
        "id": release_id,
        "title": title,
        "status": status,
        "date": date,
        "country": country,
        "medium-list": [{"format": "CD", "track-count": track_count}],
    }


def full_release_for(
    release_id,
    title,
    *,
    date="1970-01-01",
    status="Official",
    country="US",
    tracks=None,
):
    tracks = tracks if tracks is not None else ["Track 1", "Track 2", "Track 3", "Track 4"]
    return {
        "id": release_id,
        "title": title,
        "status": status,
        "date": date,
        "country": country,
        "label-info-list": [{"label": {"name": "Test Label"}}],
        "medium-list": [
            {
                "format": "CD",
                "track-count": len(tracks),
                "track-list": [
                    {
                        "position": str(index),
                        "title": track,
                        "recording": {
                            "id": f"{release_id}-recording-{index}",
                            "title": track,
                        },
                    }
                    for index, track in enumerate(tracks, start=1)
                ],
            }
        ],
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
    @contextmanager
    def _mock_resolver_boundaries(
        self,
        release_groups,
        releases_by_group,
        full_releases,
        *,
        fallback_release_groups=None,
    ):
        all_release_groups = release_groups + (fallback_release_groups or [])
        with (
            patch(
                "musicbrainz_resolver.mb.search_release_groups",
                return_value=release_groups,
            ),
            patch(
                "musicbrainz_resolver.mb.search_release_groups_by_query",
                return_value=fallback_release_groups or [],
            ),
            patch(
                "musicbrainz_resolver.mb.get_release_group_by_id",
                side_effect=lambda release_group_id: next(
                    item for item in all_release_groups if item["id"] == release_group_id
                ),
            ),
            patch(
                "musicbrainz_resolver.mb.get_releases_for_group",
                side_effect=lambda release_group_id: releases_by_group.get(release_group_id, []),
            ),
            patch(
                "musicbrainz_resolver.mb.get_release_by_id",
                side_effect=lambda release_id: full_releases.get(release_id),
            ),
            patch(
                "musicbrainz_resolver.mb.get_cover_art_url",
                return_value=None,
            ),
        ):
            yield

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
                "musicbrainz_resolver.mb.search_release_groups",
                return_value=[release_group()],
            ) as search_release_groups,
            patch(
                "musicbrainz_resolver.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
            patch(
                "musicbrainz_resolver.mb.get_releases_for_group",
                return_value=release_summaries,
            ) as get_releases_for_group,
            patch(
                "musicbrainz_resolver.mb.get_release_by_id",
                return_value=full_release(),
            ) as get_release_by_id,
            patch(
                "musicbrainz_resolver.mb.get_cover_art_url",
                return_value="https://example.test/cover.jpg",
            ),
        ):
            album = metadata.get_album_metadata("Test Artist", "Test Album")

        search_release_groups.assert_called_once_with(
            "Test Artist",
            "Test Album",
            limit=metadata.RELEASE_GROUP_SEARCH_LIMIT,
        )
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
                "musicbrainz_resolver.mb.search_release_by_spotify_url",
                return_value=spotify_release,
            ) as search_release_by_spotify_url,
            patch(
                "musicbrainz_resolver.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
            patch(
                "musicbrainz_resolver.mb.search_release_groups",
            ) as search_release_groups,
            patch(
                "musicbrainz_resolver.mb.get_release_by_id",
                return_value=full_release(),
            ) as get_release_by_id,
            patch(
                "musicbrainz_resolver.mb.get_cover_art_url",
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

    def test_resolver_uses_disambiguation_and_fallback_for_blackstar(self):
        initial_release_groups = [
            release_group_for(
                "blackstar-radio-edits",
                "Blackstar Radio Edits",
                artist="David Bowie",
                primary_type="Single",
                score=100,
                first_release_date=None,
            ),
            release_group_for(
                "talib-blackstar",
                "Blackstar",
                artist="Talib Kweli / Lupe Fiasco",
                score=59,
                first_release_date="2020-01-17",
            ),
        ]
        fallback_release_groups = [
            release_group_for(
                "bowie-blackstar-single",
                "\u2605",
                artist="David Bowie",
                primary_type="Single",
                score=100,
                first_release_date="2015-11-20",
            ),
            release_group_for(
                "bowie-blackstar-album",
                "\u2605",
                artist="David Bowie",
                score=73,
                first_release_date="2016-01-08",
                disambiguation="Blackstar",
            ),
        ]
        releases_by_group = {
            "blackstar-radio-edits": [
                release_summary_for(
                    "blackstar-radio-edits-release",
                    "Blackstar Radio Edits",
                    track_count=3,
                )
            ],
            "talib-blackstar": [
                release_summary_for(
                    "talib-blackstar-release",
                    "Blackstar",
                    date="2020-01-17",
                    track_count=14,
                )
            ],
            "bowie-blackstar-single": [
                release_summary_for(
                    "bowie-blackstar-single-release",
                    "\u2605",
                    date="2015-11-20",
                    track_count=2,
                )
            ],
            "bowie-blackstar-album": [
                release_summary_for(
                    "bowie-blackstar-album-release",
                    "\u2605",
                    date="2016-01-08",
                    track_count=7,
                )
            ],
        }
        full_releases = {
            "blackstar-radio-edits-release": full_release_for(
                "blackstar-radio-edits-release",
                "Blackstar Radio Edits",
                tracks=["Blackstar", "Blackstar (radio edit)", "Blackstar (video edit)"],
            ),
            "talib-blackstar-release": full_release_for(
                "talib-blackstar-release",
                "Blackstar",
                tracks=[f"Track {index}" for index in range(1, 15)],
            ),
            "bowie-blackstar-single-release": full_release_for(
                "bowie-blackstar-single-release",
                "\u2605",
                date="2015-11-20",
                tracks=["\u2605", "\u2605 (radio edit)"],
            ),
            "bowie-blackstar-album-release": full_release_for(
                "bowie-blackstar-album-release",
                "\u2605",
                date="2016-01-08",
                tracks=[f"Track {index}" for index in range(1, 8)],
            ),
        }

        with self._mock_resolver_boundaries(
            initial_release_groups,
            releases_by_group,
            full_releases,
            fallback_release_groups=fallback_release_groups,
        ), patch(
            "musicbrainz_resolver.mb.search_release_groups_by_query",
            return_value=fallback_release_groups,
        ) as fallback_search:
            album = metadata.get_album_metadata("David Bowie", "Blackstar")

        fallback_search.assert_called_once_with(
            'artist:"David Bowie" AND Blackstar',
            limit=metadata.RELEASE_GROUP_SEARCH_LIMIT,
        )
        self.assertEqual(album["release_group_mbid"], "bowie-blackstar-album")
        self.assertEqual(album["name"], "\u2605")
        self.assertIn(
            "Matched album title via MusicBrainz disambiguation.",
            album["_musicbrainz_match"]["reasons"],
        )

    def test_resolver_uses_alias_title_without_broad_fallback(self):
        release_groups = [
            release_group_for(
                "unrelated-exact-title",
                "Alias Album",
                artist="Different Artist",
                score=100,
            ),
            release_group_for(
                "symbol-title",
                "\u2605",
                artist="Alias Artist",
                score=84,
                aliases=["Alias Album"],
            ),
        ]
        releases_by_group = {
            "unrelated-exact-title": [
                release_summary_for("unrelated-exact-title-release", "Alias Album")
            ],
            "symbol-title": [
                release_summary_for("symbol-title-release", "\u2605")
            ],
        }
        full_releases = {
            "unrelated-exact-title-release": full_release_for(
                "unrelated-exact-title-release",
                "Alias Album",
            ),
            "symbol-title-release": full_release_for("symbol-title-release", "\u2605"),
        }

        with (
            patch(
                "musicbrainz_resolver.mb.search_release_groups",
                return_value=release_groups,
            ),
            patch(
                "musicbrainz_resolver.mb.search_release_groups_by_query",
                return_value=[],
            ) as fallback_search,
            patch(
                "musicbrainz_resolver.mb.get_release_group_by_id",
                side_effect=lambda release_group_id: next(
                    item for item in release_groups if item["id"] == release_group_id
                ),
            ),
            patch(
                "musicbrainz_resolver.mb.get_releases_for_group",
                side_effect=lambda release_group_id: releases_by_group.get(release_group_id, []),
            ),
            patch(
                "musicbrainz_resolver.mb.get_release_by_id",
                side_effect=lambda release_id: full_releases.get(release_id),
            ),
            patch("musicbrainz_resolver.mb.get_cover_art_url", return_value=None),
        ):
            album = metadata.get_album_metadata("Alias Artist", "Alias Album")

        fallback_search.assert_not_called()
        self.assertEqual(album["release_group_mbid"], "symbol-title")
        self.assertIn(
            "Matched album title via MusicBrainz alias.",
            album["_musicbrainz_match"]["reasons"],
        )

    def test_resolver_skips_broad_fallback_for_strong_initial_album_match(self):
        release_groups = [release_group_for("strong-group", "Test Album")]
        releases_by_group = {
            "strong-group": [release_summary_for("strong-release", "Test Album")]
        }
        full_releases = {
            "strong-release": full_release_for("strong-release", "Test Album")
        }

        with (
            self._mock_resolver_boundaries(
                release_groups,
                releases_by_group,
                full_releases,
            ),
            patch(
                "musicbrainz_resolver.mb.search_release_groups_by_query",
                return_value=[],
            ) as fallback_search,
        ):
            album = metadata.get_album_metadata("Test Artist", "Test Album")

        fallback_search.assert_not_called()
        self.assertEqual(album["release_group_mbid"], "strong-group")

    def test_resolver_prefers_actual_purple_rain_over_subset_live_title(self):
        release_groups = [
            release_group_for(
                "purple-rain-debut",
                "Purple Rain Debut",
                artist="Prince",
                secondary_types=["Live"],
                score=100,
                first_release_date="2020",
            ),
            release_group_for(
                "purple-rain",
                "Purple Rain",
                artist="Prince & The Revolution",
                secondary_types=["Soundtrack"],
                score=93,
                first_release_date="1984-06-25",
            ),
        ]
        releases_by_group = {
            "purple-rain-debut": [
                release_summary_for(
                    "purple-rain-debut-release",
                    "Purple Rain Debut",
                    date="2020",
                    track_count=0,
                )
            ],
            "purple-rain": [
                release_summary_for(
                    "purple-rain-release",
                    "Purple Rain",
                    date="1984-06-25",
                    track_count=9,
                )
            ],
        }
        full_releases = {
            "purple-rain-debut-release": full_release_for(
                "purple-rain-debut-release",
                "Purple Rain Debut",
                tracks=[],
            ),
            "purple-rain-release": full_release_for(
                "purple-rain-release",
                "Purple Rain",
                date="1984-06-25",
                tracks=[
                    "Let's Go Crazy",
                    "Take Me With U",
                    "The Beautiful Ones",
                    "Computer Blue",
                    "Darling Nikki",
                    "When Doves Cry",
                    "I Would Die 4 U",
                    "Baby I'm a Star",
                    "Purple Rain",
                ],
            ),
        }

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata("Prince", "Purple Rain")

        self.assertEqual(album["release_group_mbid"], "purple-rain")
        self.assertEqual(album["release_mbid"], "purple-rain-release")
        self.assertGreaterEqual(album["_musicbrainz_match"]["confidence"], 80)

    def test_resolver_prefers_plain_aerosmith_album_over_live_compilation(self):
        release_groups = [
            release_group_for(
                "aerosmith-live",
                "Aerosmith",
                artist="Aerosmith",
                secondary_types=["Compilation", "Live"],
                score=100,
                first_release_date="1996",
            ),
            release_group_for(
                "aerosmith-original",
                "Aerosmith",
                artist="Aerosmith",
                score=100,
                first_release_date="1973-01-05",
            ),
        ]
        releases_by_group = {
            "aerosmith-live": [
                release_summary_for("aerosmith-live-release", "Aerosmith", date="1996")
            ],
            "aerosmith-original": [
                release_summary_for(
                    "aerosmith-original-release",
                    "Aerosmith",
                    date="1973-01-05",
                )
            ],
        }
        full_releases = {
            "aerosmith-live-release": full_release_for(
                "aerosmith-live-release",
                "Aerosmith",
                date="1996",
            ),
            "aerosmith-original-release": full_release_for(
                "aerosmith-original-release",
                "Aerosmith",
                date="1973-01-05",
            ),
        }

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata("Aerosmith", "Aerosmith")

        self.assertEqual(album["release_group_mbid"], "aerosmith-original")

    def test_resolver_rejects_single_title_overmatch_for_are_you_experienced(self):
        release_groups = [
            release_group_for(
                "fire-single",
                "Fire / Are You Experienced",
                artist="Jimi Hendrix",
                primary_type="Single",
                secondary_types=["Live"],
                score=100,
                first_release_date="1982-09-17",
            ),
            release_group_for(
                "are-you-experienced",
                "Are You Experienced",
                artist="The Jimi Hendrix Experience",
                score=98,
                first_release_date="1967-05-12",
            ),
        ]
        releases_by_group = {
            "fire-single": [
                release_summary_for(
                    "fire-single-release",
                    "Fire / Are You Experienced",
                    date="1982-09-17",
                    track_count=2,
                )
            ],
            "are-you-experienced": [
                release_summary_for(
                    "are-you-experienced-release",
                    "Are You Experienced",
                    date="1967-05-12",
                    track_count=11,
                )
            ],
        }
        full_releases = {
            "fire-single-release": full_release_for(
                "fire-single-release",
                "Fire / Are You Experienced",
                tracks=["Fire", "Are You Experienced"],
            ),
            "are-you-experienced-release": full_release_for(
                "are-you-experienced-release",
                "Are You Experienced",
                date="1967-05-12",
                tracks=[f"Track {index}" for index in range(1, 12)],
            ),
        }

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata("Jimi Hendrix", "Are You Experienced")

        self.assertEqual(album["release_group_mbid"], "are-you-experienced")

    def test_resolver_prefers_legend_over_the_legend_for_remastered_input(self):
        release_groups = [
            release_group_for(
                "the-legend",
                "The Legend",
                artist="Bob Marley & The Wailers",
                secondary_types=["Compilation"],
                score=100,
                first_release_date="2008",
            ),
            release_group_for(
                "legend",
                "Legend",
                artist="Bob Marley & The Wailers",
                secondary_types=["Compilation"],
                score=92,
                first_release_date="1984",
            ),
        ]
        releases_by_group = {
            "the-legend": [release_summary_for("the-legend-release", "The Legend", date="2008")],
            "legend": [release_summary_for("legend-release", "Legend", date="1984")],
        }
        full_releases = {
            "the-legend-release": full_release_for("the-legend-release", "The Legend", date="2008"),
            "legend-release": full_release_for("legend-release", "Legend", date="1984"),
        }

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata(
                "Bob Marley & The Wailers",
                "Legend (The Definitive Remasters)",
            )

        self.assertEqual(album["release_group_mbid"], "legend")

    def test_resolver_falls_back_when_top_release_group_has_no_usable_release(self):
        release_groups = [
            release_group_for("bad-group", "Test Album", artist="Test Artist", score=100),
            release_group_for("good-group", "Test Album", artist="Test Artist", score=95),
        ]
        releases_by_group = {
            "bad-group": [],
            "good-group": [release_summary_for("good-release", "Test Album")],
        }
        full_releases = {"good-release": full_release_for("good-release", "Test Album")}

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata("Test Artist", "Test Album")

        self.assertEqual(album["release_group_mbid"], "good-group")

    def test_resolver_returns_low_confidence_best_guess_with_diagnostics(self):
        release_groups = [
            release_group_for(
                "weak-group",
                "Distant Title",
                artist="Different Artist",
                primary_type="Album",
                score=45,
            )
        ]
        releases_by_group = {
            "weak-group": [release_summary_for("weak-release", "Distant Title")]
        }
        full_releases = {"weak-release": full_release_for("weak-release", "Distant Title")}

        with self._mock_resolver_boundaries(release_groups, releases_by_group, full_releases):
            album = metadata.get_album_metadata("Needle Artist", "Needle Album")

        self.assertEqual(album["release_group_mbid"], "weak-group")
        self.assertLess(album["_musicbrainz_match"]["confidence"], 70)
        self.assertTrue(album["_musicbrainz_match"]["warnings"])

    def test_get_album_metadata_returns_empty_dict_when_no_match(self):
        with (
            patch(
                "musicbrainz_resolver.mb.search_release_groups",
                return_value=[],
            ),
            patch(
                "musicbrainz_resolver.mb.search_release_groups_by_query",
                return_value=[],
            ),
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
                "musicbrainz_resolver.mb.search_release_groups",
                return_value=[release_group()],
            ),
            patch(
                "musicbrainz_resolver.mb.get_release_group_by_id",
                return_value=release_group(),
            ),
            patch(
                "musicbrainz_resolver.mb.get_releases_for_group",
                return_value=release_summaries,
            ),
            patch(
                "musicbrainz_resolver.mb.get_release_by_id",
                return_value=full_release(),
            ),
            patch(
                "musicbrainz_resolver.mb.get_cover_art_url",
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
