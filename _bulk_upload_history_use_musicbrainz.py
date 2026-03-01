import pandas as pd
import musicbrainzngs
import json
import re
import time
from datetime import datetime
from unidecode import unidecode
from rapidfuzz import fuzz

file_path = "/Users/jacobbattenberg/Downloads/Albums Listened To - Sheet1.csv"

# ---------------------------
# MusicBrainz Setup
# ---------------------------
musicbrainzngs.set_useragent("AlbumTracker", "1.0", "your_email@example.com")

# Explicit rate-limiting (seconds between requests)
REQUEST_DELAY = 1.5
MAX_RETRIES = 3


# ---------------------------
# CSV Loader
# ---------------------------
def load_csv_data_to_dict(file_path: str):
    data = pd.read_csv(file_path)
    data = data.iloc[:452, :11]
    result = []
    for _, row in data.iterrows():
        artist = row.iloc[0]
        albums_in_row = [i for i in row.iloc[1:].to_list() if pd.notna(i)]
        for album in albums_in_row:
            result.append((artist, album))
    return result


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
# Release Group Search
# ---------------------------
def search_release_groups(artist: str, album: str):
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            result = musicbrainzngs.search_release_groups(
                releasegroup=album, artist=artist, limit=10
            )
            return result.get("release-group-list", [])
        except musicbrainzngs.NetworkError as e:
            print(
                f"NetworkError searching release groups for {artist} - {album}, attempt {attempt+1}"
            )
            time.sleep(3)
    print(f"Failed to search release groups for {artist} - {album}, skipping.")
    return []


def compute_match_score(candidate, artist, album):
    candidate_artist = normalize(candidate["artist-credit"][0]["name"])
    candidate_album = normalize(candidate["title"])
    artist_score = fuzz.token_set_ratio(candidate_artist, normalize(artist))
    album_score = fuzz.token_set_ratio(candidate_album, normalize(album))
    return (album_score * 0.8) + (artist_score * 0.2)


def choose_best_release_group(candidates, artist, album, threshold=75):
    if not candidates:
        return None

    # Compute fuzzy match scores
    scored = [(compute_match_score(c, artist, album), c) for c in candidates]
    scored.sort(reverse=True, key=lambda x: x[0])

    # Keep only candidates above threshold
    scored = [(score, c) for score, c in scored if score >= threshold]
    if not scored:
        return None

    # Prefer primary types: Album > EP > others
    def type_priority(candidate):
        ptype = candidate.get("primary-type", "").lower()
        if ptype == "album":
            return 2
        elif ptype == "ep":
            return 1
        else:
            return 0

    scored.sort(key=lambda x: (type_priority(x[1]), x[0]), reverse=True)

    # Return highest-priority, highest-score candidate
    return scored[0][1]


# ---------------------------
# Release Selection for Art
# ---------------------------
def get_releases_for_group(release_group_mbid):
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            result = musicbrainzngs.search_releases(rgid=release_group_mbid, limit=100)
            return result.get("release-list", [])
        except musicbrainzngs.NetworkError:
            print(
                f"NetworkError fetching releases for {release_group_mbid}, attempt {attempt+1}"
            )
            time.sleep(3)
    print(f"Failed to fetch releases for {release_group_mbid}, skipping.")
    return []


def choose_best_release(releases, album_title: str):
    if not releases:
        return None
    # 1. Prefer official
    official = [r for r in releases if r.get("status") == "Official"] or releases
    # 2. Prefer exact title
    exact_title_matches = [
        r
        for r in official
        if r.get("title", "").strip().lower() == album_title.strip().lower()
    ]
    official = exact_title_matches if exact_title_matches else official
    # 3. Prefer digital
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
    # 4. Earliest release date
    candidates.sort(key=lambda r: r.get("date", "9999-99-99"))
    # 5. Tie-breaker: US release
    earliest_date = candidates[0].get("date", "9999-99-99")
    earliest_candidates = [
        r for r in candidates if r.get("date", "9999-99-99") == earliest_date
    ]
    if len(earliest_candidates) > 1:
        us_candidates = [r for r in earliest_candidates if r.get("country") == "US"]
        if us_candidates:
            return us_candidates[0]
    return candidates[0]


def get_cover_art_url(release_mbid):
    return f"https://coverartarchive.org/release/{release_mbid}/front"


# ---------------------------
# Tracklist, Tags, Wikipedia
# ---------------------------
def get_full_release(release_id):
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            return musicbrainzngs.get_release_by_id(
                release_id, includes=["recordings"]
            )["release"]
        except musicbrainzngs.NetworkError:
            print(f"NetworkError fetching full release {release_id}")
            time.sleep(3)
    return None


def extract_tracklist(release):
    tracklist = []
    for medium in release.get("medium-list", []):
        for track in medium.get("track-list", []):
            tracklist.append(
                {
                    "position": track.get("position"),
                    "title": track.get("recording", {}).get("title"),
                    "recording_mbid": track.get("recording", {}).get("id"),
                }
            )
    return tracklist


def extract_tags(release_group_mbid):
    tags = []
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            rg_data = musicbrainzngs.get_release_group_by_id(
                release_group_mbid, includes=["tags", "url-rels"]
            )["release-group"]
            tags = [t["name"] for t in rg_data.get("tag-list", [])]
            return tags
        except musicbrainzngs.NetworkError:
            print(f"NetworkError fetching tags for {release_group_mbid}")
            time.sleep(3)
    return tags


def extract_label(release):
    labels = release.get("label-info-list", [])
    if len(labels) == 0:
        return None
    label_name = labels[0].get("label", {}).get("name", None)
    return label_name


# ---------------------------
# Album Processor
# ---------------------------
def process_album(artist: str, album: str):
    candidates = search_release_groups(artist, album)
    best_group = choose_best_release_group(candidates, artist, album)

    if not best_group:
        print(f"No match for {artist} - {album}")
        return None

    release_group_mbid = best_group["id"]
    canonical_artist = best_group["artist-credit"][0]["name"]
    artist_mbid = best_group["artist-credit"][0]["artist"]["id"]
    canonical_title = best_group["title"]
    first_release_date = best_group.get("first-release-date")

    # Fetch all releases and pick the best one for both metadata and image
    releases = get_releases_for_group(release_group_mbid)
    chosen_release = choose_best_release(releases, canonical_title)

    if not chosen_release:
        print(f"No suitable release found for {artist} - {album}")
        return None

    # Cover art
    image_url = get_cover_art_url(chosen_release["id"])

    # Tracklist
    full_release = get_full_release(chosen_release["id"])
    tracklist = extract_tracklist(full_release)

    # Label
    label = extract_label(chosen_release)

    # Tags and Wikipedia
    tags = extract_tags(release_group_mbid)

    # Split release date into year/month/day
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
        "original_release_date": first_release_date,
        "release_year": int(year) if year else None,
        "release_month": int(month) if month else None,
        "release_day": int(day) if day else None,
        "tracklist": tracklist,
        "tags": tags,
        "image_url": image_url,
        "listen_date": None,
        "source": "musicbrainz bulk upload",
    }


# ---------------------------
# Bulk Processor
# ---------------------------
def get_album_data(entries: list):
    album_state = {
        "last_checked": datetime.utcnow().isoformat(),
        "completed_albums": {},
    }
    unmatched = []

    import random

    entries = random.sample(entries, 10)

    for i, (artist, album) in enumerate(entries, start=1):
        record = process_album(artist, album)
        if record:
            key = f"{record['artist']} - {record['name']}"
            album_state["completed_albums"][key] = record
        else:
            unmatched.append((artist, album))

        if i % 25 == 0:
            print(f"Processed {i} albums out of {len(entries)}")

    if unmatched:
        with open("unmatched_musicbrainz.csv", "w", encoding="utf-8") as f:
            for artist, album in unmatched:
                f.write(f"{artist},{album}\n")

    return album_state


# ---------------------------
# Main
# ---------------------------
def main():
    entries_raw = load_csv_data_to_dict(file_path)
    import random

    entries = random.sample(entries_raw, 10)
    entries.append(entries_raw[43])

    album_data = get_album_data(entries)

    with open("google_sheets_album_state_musicbrainz.json", "w", encoding="utf-8") as f:
        json.dump(album_data, f, indent=2)
    print(
        f"Wrote {len(album_data['completed_albums'])} albums to album_state_migrated.json"
    )


if __name__ == "__main__":
    main()
