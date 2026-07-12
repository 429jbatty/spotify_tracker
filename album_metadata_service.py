import pandas as pd
import json
from datetime import datetime
from rapidfuzz import fuzz

import logging
from collections import Counter

from musicbrainz_resolver import (
    CANONICAL_AUTO_APPLY_CONFIDENCE,
    IMPORT_MATCH_CONFIDENCE,
    MATCH_ALGORITHM_VERSION,
    RELEASE_GROUP_SEARCH_LIMIT,
    _artist_credit_display,
    _rank_release_groups,
    _search_normalize,
    _title_match_score,
    match_diagnostics,
    metadata_match_confidence,
    normalize,
    resolve_musicbrainz_candidate,
    resolve_spotify_candidate,
)

logger = logging.getLogger(__name__)

ENRICHED_CREDIT_INGESTION_VERSION = "musicbrainz_credit_v2"

# ---------------------------
# Release Group Matching
# ---------------------------


def compute_match_score(candidate, artist, album):
    candidate_artist = _artist_credit_display(candidate.get("artist-credit"))
    album_score, _, _ = _title_match_score(candidate.get("title", ""), album)
    artist_score = fuzz.token_set_ratio(
        _search_normalize(candidate_artist),
        _search_normalize(artist),
    )

    return (album_score * 0.8) + (artist_score * 0.2)


def choose_best_release_group(candidates, artist, album, threshold=75):
    if not candidates:
        return None

    ranked = _rank_release_groups(candidates, artist, album, "canonical")
    scored = [(item.score, item.release_group) for item in ranked]
    scored.sort(reverse=True, key=lambda x: x[0])

    scored = [(score, c) for score, c in scored if score >= threshold]
    if not scored:
        return None

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


def _extract_credit_attributes(raw_credit):
    attributes = []
    for attr in raw_credit.get("attributes", []):
        if isinstance(attr, dict):
            value = attr.get("attribute")
        else:
            value = attr
        if value:
            attributes.append(str(value))
    return attributes


def _credit_role(credit_type: str, source_scope: str) -> str:
    if source_scope == "work":
        return f"work {credit_type}"
    return credit_type


def _extract_artist_relation_credits(relations, source_scope: str = "recording"):
    credits = []
    for raw_credit in relations:
        credit_type = raw_credit.get("type")
        artist = raw_credit.get("artist", {})
        name = artist.get("name")
        if not credit_type or not name:
            continue

        attributes = _extract_credit_attributes(raw_credit)
        artist_mbid = artist.get("id")
        credits.append(
            {
                "name": name,
                "artist_mbid": artist_mbid,
                "role": _credit_role(credit_type, source_scope),
                "raw_credit_type": credit_type,
                "attributes": attributes,
                "source_scope": source_scope,
                "identity_resolution": "mbid" if artist_mbid else "normalized_name",
                "ingestion_version": ENRICHED_CREDIT_INGESTION_VERSION,
            }
        )

    return credits


def _extract_recording_credits(recording: dict):
    """
    Extract key album credits from a MusicBrainz release object.
    Returns a dict with lists for each role: artist, producer, mixing, mastering.
    """
    if recording == {}:
        logging.info(f"No recording credits found for recording: {recording.get('id')}")
        return {}

    credits = _extract_artist_relation_credits(recording.get("artist-relation-list", []))

    for work_relation in recording.get("work-relation-list", []):
        work = work_relation.get("work", {})
        credits.extend(
            _extract_artist_relation_credits(
                work.get("artist-relation-list", []),
                source_scope="work",
            )
        )

    return credits or {}


def _artist_credit_name(artist_credit):
    return (
        artist_credit.get("name")
        or artist_credit.get("artist", {}).get("name")
        or artist_credit.get("artist", {}).get("sort-name")
    )


def _resolve_release(artist: str, album: str, spotify_url: str | None = None):
    """
    Returns: (release_group, chosen_release, image_url)
    """
    resolved = resolve_spotify_candidate(spotify_url, "canonical")
    if resolved is None:
        resolved = resolve_musicbrainz_candidate(
            artist,
            album,
            lookup_intent="canonical",
            include_cover_art=True,
        )

    if not resolved:
        return None, None, None

    return resolved.release_group, resolved.release, resolved.image_url


def _album_record_from_candidate(candidate, lookup_intent: str) -> dict:
    record = _build_album_record(
        candidate.release_group,
        candidate.release,
        candidate.image_url,
    )
    record["_musicbrainz_match"] = match_diagnostics(candidate, lookup_intent)
    return record


def get_album_metadata(artist: str, album: str, spotify_url: str | None = None):
    candidate = resolve_spotify_candidate(spotify_url, "canonical")
    if candidate is None:
        candidate = resolve_musicbrainz_candidate(
            artist,
            album,
            lookup_intent="canonical",
            include_cover_art=True,
        )

    if not candidate:
        logging.warning(f"No metadata found for {artist} - {album}")
        return {}

    album_record = _album_record_from_candidate(candidate, "canonical")

    # log any null values from metadata pull
    for key, value in album_record.items():
        if value is None:
            logging.warning(f"Null value for {key} in {artist} - {album}")

    return album_record


def get_album_metadata_for_import_matching(artist: str, album: str):
    candidate = resolve_musicbrainz_candidate(
        artist,
        album,
        lookup_intent="import_matching",
        include_cover_art=False,
    )

    if not candidate:
        logging.warning(f"No metadata found for {artist} - {album}")
        return {}

    return _album_record_from_candidate(candidate, "import_matching")


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
