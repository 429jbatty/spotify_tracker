import utils as util
from spotify_manager import SpotifyAPI
import pandas as pd
import os
from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
import time
import csv
import json
from datetime import datetime
import re
from unidecode import unidecode
from rapidfuzz import fuzz

file_path = "/Users/jacobbattenberg/Downloads/Albums Listened To - Sheet1.csv"
scopes = ["user-read-recently-played"]

sp_oauth = SpotifyOAuth(
    client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
    client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
    scope=" ".join(scopes),
    cache_handler=None,  # disable .cache file
)
token_info = sp_oauth.refresh_access_token(os.environ.get("SPOTIFY_REFRESH_TOKEN"))
sp = Spotify(auth=token_info["access_token"])


def load_csv_data_to_dict(file_path: str):
    data = pd.read_csv(file_path)
    data = data.iloc[:452, :11]

    result = []
    for _, row in data.iterrows():
        artist = row.iloc[0]
        albums_in_row = row.iloc[1:].to_list()
        albums_in_row = [i for i in albums_in_row if pd.notna(i)]
        for album in albums_in_row:
            result.append((artist, album))

    return result


# ---------------------------
# Spotify Search Logic
# ---------------------------


def search_exact(sp, artist: str, album: str, limit: int = 5):
    query = f'album:"{album}" artist:"{artist}"'
    return sp.search(q=query, type="album", limit=limit)


def search_general(sp, artist: str, album: str, limit: int = 5):
    query = album + " " + artist
    return sp.search(q=query, type="album", limit=limit)


def normalize_results(search_results):
    """
    Extracts the album list safely from Spotify response.
    """
    return search_results.get("albums", {}).get("items", [])


def search_album(sp, artist: str, album: str):
    raw_results_exact = search_exact(sp, artist, album)
    results_exact = normalize_results(raw_results_exact)
    if len(results_exact) > 0:
        return normalize_results(raw_results_exact)
    else:
        raw_results_general = search_general(sp, artist, album)
        return normalize_results(raw_results_general)


# ---------------------------
# Matching Logic
# ---------------------------


def is_exact_match(result, artist: str, album: str) -> bool:
    spotify_artist = result["artists"][0]["name"].lower()
    spotify_album = result["name"].lower()

    return spotify_artist == artist.lower() and spotify_album == album.lower()


def normalize(text: str) -> str:
    text = unidecode(text.lower())
    text = text.replace("&", "and")
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def compute_match_score(result, artist: str, album: str) -> float:
    spotify_artist = normalize(result["artists"][0]["name"])
    spotify_album = normalize(result["name"])

    target_artist = normalize(artist)
    target_album = normalize(album)

    artist_score = fuzz.token_set_ratio(spotify_artist, target_artist)
    album_score = fuzz.token_set_ratio(spotify_album, target_album)

    # Penalize non-album types slightly
    album_type_penalty = 0
    if result.get("album_type") != "album":
        album_type_penalty = 10

    # Weight album name more heavily
    score = (album_score * 0.8) + (artist_score * 0.2)

    return score - album_type_penalty


def choose_best_match(results, artist: str, album: str, threshold: float = 75):
    if not results:
        return None

    scored_results = []

    for result in results:
        score = compute_match_score(result, artist, album)
        scored_results.append((score, result))

    scored_results.sort(reverse=True, key=lambda x: x[0])

    best_score, best_result = scored_results[0]

    # Optional debug
    # print(f"{artist} - {album} → {best_result['name']} ({best_score:.1f})")

    if best_score >= threshold:
        return best_result

    return None


# ---------------------------
# Formatting Logic
# ---------------------------


def extract_image_url(album_data):
    images = album_data.get("images", [])
    return images[0]["url"] if images else None


def format_album_record(album_data):
    """
    Converts Spotify album object into your new JSON structure.
    """
    return {
        "artist": album_data["artists"][0]["name"],
        "name": album_data["name"],
        "release_date": album_data.get("release_date"),
        "label": album_data.get("label"),
        "image_url": extract_image_url(album_data),
        "listen_history": [],
        "source": "spotify bulk upload",
    }


# ---------------------------
# Main Processing Loop
# ---------------------------


def process_entry(sp, artist: str, album: str):
    results = search_album(sp, artist, album)
    best_match = choose_best_match(results, artist, album)

    if not best_match:
        print(f"No match found for: {artist} - {album}")
        return None

    album_metadata = sp.album(best_match["id"])

    return format_album_record(album_metadata)


def main():
    entries = load_csv_data_to_dict(file_path)

    migrated_json = {
        "last_checked": datetime.utcnow().isoformat(),
        "completed_albums": {},
    }
    unmatched = []

    for artist, album in entries:
        time.sleep(0.1)  # avoid spotify rate limiting
        record = process_entry(sp, artist, album)
        if record:
            key = f"{record['artist']} - {record['name']}"
            migrated_json["completed_albums"][key] = record
        else:
            unmatched.append((artist, album))

    # Write unmatched albums to CSV
    if unmatched:
        with open("unmatched_albums.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["artist", "album"])
            writer.writerows(unmatched)
        print(f"Wrote {len(unmatched)} unmatched albums to unmatched_albums.csv")

    # Write migrated JSON
    with open("google_sheets_album_state.json", "w", encoding="utf-8") as f:
        json.dump(migrated_json, f, indent=2)
    print(
        f"Wrote {len(migrated_json['completed_albums'])} albums to album_state_migrated.json"
    )


if __name__ == "__main__":
    main()
