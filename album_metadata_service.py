import pandas as pd
import json
import re
from datetime import datetime
from unidecode import unidecode
from rapidfuzz import fuzz
import musicbrainzngs
import musicbrainz_client as mb

import logging
from collections import Counter

logger = logging.getLogger(__name__)

# ---------------------------
# Normalization
# ---------------------------


def normalize(text: str) -> str:
    text = unidecode(text.lower())
    text = text.replace("&", "and")
    text = re.sub(r"\(.*?deluxe.*?\)", "", text)
    text = re.sub(r"\(.*?remaster.*?\)", "", text)
    text = re.sub(r"\(.*?anniversary.*?\)", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


# ---------------------------
# Release Group Matching
# ---------------------------


def compute_match_score(candidate, artist, album):
    candidate_artist = normalize(candidate["artist-credit"][0]["name"])
    candidate_album = normalize(candidate["title"])

    artist_score = fuzz.token_set_ratio(candidate_artist, normalize(artist))
    album_score = fuzz.token_set_ratio(candidate_album, normalize(album))

    return (album_score * 0.8) + (artist_score * 0.2)


def choose_best_release_group(candidates, artist, album, threshold=75):
    if not candidates:
        return None

    scored = [(compute_match_score(c, artist, album), c) for c in candidates]
    scored.sort(reverse=True, key=lambda x: x[0])

    scored = [(score, c) for score, c in scored if score >= threshold]
    if not scored:
        return None

    def type_priority(candidate):
        ptype = candidate.get("primary-type", "").lower()
        if ptype == "album":
            return 2
        elif ptype == "ep":
            return 1
        return 0

    scored.sort(key=lambda x: (type_priority(x[1]), x[0]), reverse=True)

    return scored[0][1]


# ---------------------------
# Release Selection
# ---------------------------


def choose_best_release(releases, album_title: str):
    if not releases:
        return None

    official = [r for r in releases if r.get("status") == "Official"] or releases

    exact = [
        r
        for r in official
        if r.get("title", "").strip().lower() == album_title.strip().lower()
    ]
    official = exact if exact else official

    digital, physical = [], []
    for r in official:
        media_formats = [m.get("format", "").lower() for m in r.get("medium-list", [])]
        if any("digital" in f for f in media_formats):
            digital.append(r)
        else:
            physical.append(r)

    candidates = digital if digital else physical
    if not candidates:
        return None

    candidates.sort(key=lambda r: r.get("date", "9999-99-99"))

    earliest_date = candidates[0].get("date", "9999-99-99")
    earliest = [r for r in candidates if r.get("date", "9999-99-99") == earliest_date]

    if len(earliest) > 1:
        us = [r for r in earliest if r.get("country") == "US"]
        if us:
            return us[0]

    return candidates[0]


def _release_track_count(release):
    track_count = 0
    for medium in release.get("medium-list", []):
        track_count += int(medium.get("track-count") or 0)
    return track_count


def _date_sort_value(release):
    return release.get("date") or "9999-99-99"


def _relation_count(release):
    total = len(release.get("artist-relation-list", []))

    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            recording = track.get("recording", {})
            total += len(recording.get("artist-relation-list", []))
            for work_relation in recording.get("work-relation-list", []):
                work = work_relation.get("work", {})
                total += len(work.get("artist-relation-list", []))

    return total


def _choose_best_enriched_release(enriched_releases, album_title: str):
    if not enriched_releases:
        return None

    track_counts = [
        _release_track_count(item["release"])
        for item in enriched_releases
        if _release_track_count(item["release"]) > 0
    ]
    preferred_track_count = None
    if track_counts:
        counts = Counter(track_counts)
        preferred_track_count = sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    def score(item):
        release = item["release"]
        summary = item["summary"]
        release_title = release.get("title") or summary.get("title", "")
        media_formats = [
            medium.get("format", "").lower()
            for medium in release.get("medium-list", [])
        ]
        track_count = _release_track_count(release)

        value = 0
        if normalize(release_title) == normalize(album_title):
            value += 40
        if release.get("status") == "Official" or summary.get("status") == "Official":
            value += 20
        if item.get("image_url"):
            value += 30
        if release.get("label-info-list"):
            value += 10
        if release.get("date"):
            value += 8
        if preferred_track_count and track_count == preferred_track_count:
            value += 18
        elif preferred_track_count and track_count > preferred_track_count:
            value -= min(track_count - preferred_track_count, 10)
        if any("digital" in media_format for media_format in media_formats):
            value += 4
        if any("cd" == media_format for media_format in media_formats):
            value += 3
        if release.get("country") in {"US", "GB", "XW"}:
            value += 2

        value += min(_relation_count(release), 20)
        return value

    return sorted(
        enriched_releases,
        key=lambda item: (-score(item), _date_sort_value(item["release"])),
    )[0]


# ---------------------------
# Tracklist + Metadata
# ---------------------------


def _extract_tracks_and_credits(release):
    tracklist = []

    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            credits = _extract_recording_credits(track.get("recording", {}))
            tracklist.append(
                {
                    "position": track.get("position"),
                    "title": track.get("title")
                    or track.get("recording", {}).get("title"),
                    "credits": credits,
                    "recording_mbid": track.get("recording", {}).get("id"),
                }
            )

    return tracklist


def _extract_artist_relation_credits(relations):
    credits = []
    for raw_credit in relations:
        credit_type = raw_credit.get("type")
        artist = raw_credit.get("artist", {})
        name = artist.get("name")
        if not credit_type or not name:
            continue

        attributes = [attr["attribute"] for attr in raw_credit.get("attributes", [])]
        attributes_str = ", ".join(attributes)
        credits.append((name, credit_type, attributes_str))

    return credits


def _extract_recording_credits(recording: dict):
    """
    Extract key album credits from a MusicBrainz release object.
    Returns a dict with lists for each role: artist, producer, mixing, mastering.
    """
    if recording == {}:
        logging.info(f"No recording credits found for recording: {recording.get('id')}")
        return {}

    credits = _extract_artist_relation_credits(
        recording.get("artist-relation-list", [])
    )

    for work_relation in recording.get("work-relation-list", []):
        work = work_relation.get("work", {})
        for name, credit_type, attributes in _extract_artist_relation_credits(
            work.get("artist-relation-list", [])
        ):
            credits.append((name, f"work {credit_type}", attributes))

    return credits or {}


def _artist_credit_name(artist_credit):
    return (
        artist_credit.get("name")
        or artist_credit.get("artist", {}).get("name")
        or artist_credit.get("artist", {}).get("sort-name")
    )


def _safe_cover_art_url(release_mbid: str, release_group_mbid: str | None = None):
    try:
        return mb.get_cover_art_url(release_mbid, release_group_mbid)
    except musicbrainzngs.NetworkError as exc:
        logger.warning(
            "Cover art lookup failed for release %s: %s",
            release_mbid,
            exc,
        )
        return None


def _resolve_release(artist: str, album: str, spotify_url: str | None = None):
    """
    Returns: (release_group, chosen_release, image_url)
    """
    # --- Path A: Spotify URL ---
    if spotify_url:
        release = mb.search_release_by_spotify_url(spotify_url)
        if release:
            release_group = release["release-group"]
            best_release_group = (
                mb.get_release_group_by_id(release_group["id"]) or release_group
            )
            full_release = mb.get_release_by_id(release["id"])
            image_url = _safe_cover_art_url(release["id"], best_release_group["id"])
            return best_release_group, full_release, image_url

    # --- Path B: Artist/Album search ---
    candidates = mb.search_release_groups(artist, album)
    best_release_group = choose_best_release_group(candidates, artist, album)

    if not best_release_group:
        return None, None, None

    best_release_group = (
        mb.get_release_group_by_id(best_release_group["id"]) or best_release_group
    )

    release_summaries = mb.get_releases_for_group(best_release_group["id"])
    official_summaries = [
        release for release in release_summaries if release.get("status") == "Official"
    ]
    release_summaries = official_summaries or release_summaries

    enriched_releases = []
    for release_summary in release_summaries:
        full_release = mb.get_release_by_id(release_summary["id"])
        image_url = _safe_cover_art_url(full_release["id"], best_release_group["id"])
        enriched_releases.append(
            {
                "summary": release_summary,
                "release": full_release,
                "image_url": image_url,
            }
        )

    chosen_release = _choose_best_enriched_release(
        enriched_releases, best_release_group["title"]
    )

    if not chosen_release:
        return None, None, None

    return best_release_group, chosen_release["release"], chosen_release["image_url"]


def get_album_metadata(artist: str, album: str, spotify_url: str | None = None):
    release_group, full_release, image_url = _resolve_release(
        artist, album, spotify_url
    )

    if not release_group or not full_release:
        logging.warning(f"No metadata found for {artist} - {album}")
        return {}

    album_record = _build_album_record(release_group, full_release, image_url)

    # log any null values from metadata pull
    for key, value in album_record.items():
        if value is None:
            logging.warning(f"Null value for {key} in {artist} - {album}")

    return album_record


def get_album_metadata_for_import_matching(artist: str, album: str):
    candidates = mb.search_release_groups(artist, album)
    best_release_group = choose_best_release_group(candidates, artist, album)

    if not best_release_group:
        logging.warning(f"No metadata found for {artist} - {album}")
        return {}

    best_release_group = (
        mb.get_release_group_by_id(best_release_group["id"]) or best_release_group
    )

    release_summaries = mb.get_releases_for_group(best_release_group["id"])
    chosen_release = choose_best_release(release_summaries, best_release_group["title"])
    if not chosen_release:
        logging.warning(f"No release found for {artist} - {album}")
        return {}

    full_release = mb.get_release_by_id(chosen_release["id"])
    if not full_release:
        logging.warning(f"No full release found for {artist} - {album}")
        return {}

    return _build_album_record(best_release_group, full_release, image_url=None)


def _build_album_record(release_group, release, image_url=None):
    release_group_mbid = release_group["id"]
    primary_artist_credit = release_group["artist-credit"][0]
    canonical_artist = _artist_credit_name(primary_artist_credit)
    artist_mbid = primary_artist_credit["artist"]["id"]
    canonical_title = release_group["title"]
    first_release_date = release_group.get("first-release-date")

    tracklist = _extract_tracks_and_credits(release)

    tags = [t["name"] for t in release_group.get("tag-list", [])]
    genres = [g["name"] for g in release_group.get("genre-list", [])]

    labels = release.get("label-info-list", [])
    label = labels[0].get("label", {}).get("name") if labels else None

    # Split date
    date_parts = (
        first_release_date.split("-") if first_release_date else [None, None, None]
    )
    year, month, day = (date_parts + [None, None, None])[:3]

    return {
        "artist": canonical_artist,
        "artist_mbid": artist_mbid,
        "name": canonical_title,
        "primary_type": release_group.get("primary-type"),
        "secondary_types": release_group.get("secondary-type-list", []),
        "release_group_mbid": release_group_mbid,
        "release_mbid": release["id"],
        "label": label,
        "release_year": int(year) if year else None,
        "release_month": int(month) if month else None,
        "release_day": int(day) if day else None,
        "tracklist": tracklist,
        "genres": genres,
        "tags": tags,
        "image_url": image_url,
        "source": "musicbrainz",
    }
