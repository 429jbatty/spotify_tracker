# musicbrainz_client.py

import socket
import time
import musicbrainzngs
import threading

# ---------------------------
# Config
# ---------------------------


musicbrainzngs.set_useragent(
    "AlbumTracker",
    "1.0",
    "your_email@example.com",
)


# Rate limiting help
RATE_LIMIT = 1.1
MAX_RETRIES = 5
REQUEST_DELAY = 1.1
REQUEST_TIMEOUT_SECONDS = 20

socket.setdefaulttimeout(REQUEST_TIMEOUT_SECONDS)

_rate_lock = threading.Lock()
_last_request_time = 0


def _rate_limited_request():
    global _last_request_time

    with _rate_lock:
        now = time.time()
        elapsed = now - _last_request_time

        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)

        _last_request_time = time.time()


def _with_retries(func, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            _rate_limited_request()
            return func(*args, **kwargs)

        except musicbrainzngs.NetworkError:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(3)


# ---------------------------
# Release Group Search
# ---------------------------


def search_release_groups(artist: str, album: str, limit: int = 25):
    result = _with_retries(
        musicbrainzngs.search_release_groups,
        releasegroup=album,
        artist=artist,
        limit=limit,
    )
    return result.get("release-group-list", [])


def search_release_groups_by_query(query: str, limit: int = 25):
    result = _with_retries(
        musicbrainzngs.search_release_groups,
        query=query,
        limit=limit,
    )
    return result.get("release-group-list", [])


def get_release_group_by_id(release_group_mbid: str):
    result = _with_retries(
        musicbrainzngs.get_release_group_by_id,
        release_group_mbid,
        includes=["artist-credits", "aliases", "tags", "url-rels"],
    )
    return result.get("release-group")


# ---------------------------
# Artist Search
# ---------------------------


def search_artists(name: str):
    result = _with_retries(
        musicbrainzngs.search_artists,
        artist=name,
        limit=10,
    )
    return result.get("artist-list", [])


# ---------------------------
# Releases
# ---------------------------


def get_releases_for_group(release_group_mbid: str):
    result = _with_retries(
        musicbrainzngs.browse_releases,
        release_group=release_group_mbid,
        includes=["artist-credits", "labels", "media"],
        release_status=["official"],
        limit=100,
    )
    return result.get("release-list", [])


def get_release_by_id(release_id: str):
    result = _with_retries(
        musicbrainzngs.get_release_by_id,
        release_id,
        includes=[
            "recordings",  # tracklist info
            "labels",  # label info
            "tags",  # genre/tags
            "artist-credits",  # main artist(s)
            "artist-rels",  # relationships for artist (optional, useful for credits)
            "release-rels",  # release-level relationships (e.g., production, mastering)
            "release-group-rels",
            "work-rels",  # track-level relationships (composer, producer, etc.)
            "work-level-rels",
            "url-rels",  # Wikipedia, Discogs links
            "recording-level-rels",
        ],
    )
    return result.get("release")


# ---------------------------
# Work
# ---------------------------


def get_work_by_id(work_id: str):
    result = _with_retries(musicbrainzngs.get_work_by_id, work_id)
    return result.get("work")


# ---------------------------
# Cover Art
# ---------------------------


def _https_url(url: str | None):
    if not url:
        return None
    return url.replace("http://", "https://", 1)


def _front_cover_url_from_images(cover_art: dict):
    images = cover_art.get("images", [])
    front_images = [img for img in images if img.get("front")]
    approved_front_images = [img for img in front_images if img.get("approved")]
    candidates = approved_front_images or front_images or images

    if not candidates:
        return None

    image = candidates[0]
    thumbnails = image.get("thumbnails", {})
    return _https_url(
        thumbnails.get("1200")
        or thumbnails.get("500")
        or thumbnails.get("large")
        or image.get("image")
    )


def get_release_cover_art_url(release_mbid: str):
    try:
        cover_art = _with_retries(musicbrainzngs.get_image_list, release_mbid)
    except musicbrainzngs.ResponseError:
        return None

    return _front_cover_url_from_images(cover_art)


def get_release_group_cover_art_url(release_group_mbid: str):
    try:
        cover_art = _with_retries(
            musicbrainzngs.get_release_group_image_list, release_group_mbid
        )
    except musicbrainzngs.ResponseError:
        return None

    return _front_cover_url_from_images(cover_art)


def get_cover_art_url(release_mbid: str, release_group_mbid: str | None = None):
    release_image = get_release_cover_art_url(release_mbid)
    if release_image:
        return release_image

    if release_group_mbid:
        return get_release_group_cover_art_url(release_group_mbid)

    return None


# musicbrain_client.py


def search_release_by_spotify_url(spotify_url: str):
    """
    Find a MusicBrainz release by Spotify URL.

    Returns the release dict if found, else None.
    """
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            # MusicBrainz can search for URLs using 'url:"<full_url>"'
            result = musicbrainzngs.search_releases(
                query=f'url:"{spotify_url}"', limit=1
            )
            release_list = result.get("release-list", [])
            if release_list:
                return release_list[0]
            return None
        except musicbrainzngs.NetworkError:
            print(
                f"NetworkError searching for Spotify URL {spotify_url}, attempt {attempt+1}"
            )
            time.sleep(3)
    return None
