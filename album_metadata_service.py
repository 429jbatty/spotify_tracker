import pandas as pd
import json
import re
from datetime import datetime
from unidecode import unidecode
from rapidfuzz import fuzz
import musicbrainz_client as mb

import logging

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
                    "title": track.get("recording", {}).get("title"),
                    "credits": credits,
                    "recording_mbid": track.get("recording", {}).get("id"),
                }
            )

    return tracklist


def _extract_recording_credits(recording: dict) -> dict:
    """
    Extract key album credits from a MusicBrainz release object.
    Returns a dict with lists for each role: artist, producer, mixing, mastering.
    """
    if recording == {} or "artist-relation-list" not in recording:
        logging.info(f"No recording credits found for recording: {recording.get('id')}")
        return {}

    raw_credits = recording["artist-relation-list"]

    credits = []
    for raw_credit in raw_credits:
        credit_type = raw_credit["type"]
        name = raw_credit["artist"]["name"]
        attributes = [attr["attribute"] for attr in raw_credit.get("attributes", [])]
        attributes_str = ", ".join(attributes)
        credits.append((name, credit_type, attributes_str))

    return credits


def _resolve_release(artist: str, album: str, spotify_url: str | None = None):
    """
    Returns: (release_group, chosen_release, full_release)
    """
    # --- Path A: Spotify URL ---
    if spotify_url:
        release = mb.search_release_by_spotify_url(spotify_url)
        if release:
            best_release_group = release["release-group"]
            full_release = mb.get_release_by_id(release["id"])
            return best_release_group, full_release

    # --- Path B: Artist/Album search ---
    candidates = mb.search_release_groups(artist, album)
    best_release_group = choose_best_release_group(candidates, artist, album)

    if not best_release_group:
        return None, None

    release_summaries = mb.get_releases_for_group(best_release_group["id"])
    chosen_release_summary = choose_best_release(
        release_summaries, best_release_group["title"]
    )

    if not chosen_release_summary:
        return None, None

    full_release = mb.get_release_by_id(chosen_release_summary["id"])

    return best_release_group, full_release


def get_album_metadata(artist: str, album: str, spotify_url: str | None = None):
    release_group, full_release = _resolve_release(artist, album, spotify_url)

    if not release_group or not full_release:
        logging.warning(f"No metadata found for {artist} - {album}")
        return {}

    album_record = _build_album_record(release_group, full_release)

    # log any null values from metadata pull
    for key, value in album_record.items():
        if value is None:
            logging.warning(f"Null value for {key} in {artist} - {album}")

    return album_record


def _build_album_record(release_group, release):
    release_group_mbid = release_group["id"]
    canonical_artist = release_group["artist-credit"][0]["name"]
    artist_mbid = release_group["artist-credit"][0]["artist"]["id"]
    canonical_title = release_group["title"]
    first_release_date = release_group.get("first-release-date")

    tracklist = _extract_tracks_and_credits(release)

    tags = [t["name"] for t in release_group.get("tag-list", [])]

    labels = release.get("label-info-list", [])
    label = labels[0].get("label", {}).get("name") if labels else None

    image_url = mb.get_cover_art_url(release["id"])

    # Split date
    date_parts = (
        first_release_date.split("-") if first_release_date else [None, None, None]
    )
    year, month, day = (date_parts + [None, None, None])[:3]

    return {
        "artist": canonical_artist,
        "artist_mbid": artist_mbid,
        "name": canonical_title,
        "release_group_mbid": release_group_mbid,
        "label": label,
        "release_year": int(year) if year else None,
        "release_month": int(month) if month else None,
        "release_day": int(day) if day else None,
        "tracklist": tracklist,
        "tags": tags,
        "image_url": image_url,
        "source": "musicbrainz",
    }
