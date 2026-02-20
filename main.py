import os
import json
import datetime
from collections import defaultdict
from dotenv import load_dotenv

from spotify_manager import SpotifyAPI

STATE_FILE = "album_state.json"

load_dotenv()

# ==============================
# ---- Utility / Persistence ----
# ==============================


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_checked": None, "albums_in_progress": {}, "completed_albums": {}}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_local_credentials():
    """
    You can replace this with env vars later for GitHub Actions.
    """
    return {
        "client_id": os.environ.get("SPOTIFY_CLIENT_ID"),
        "client_secret": os.environ.get("SPOTIFY_CLIENT_SECRET"),
        "redirect_uri": os.environ.get("SPOTIFY_REDIRECT_URI"),
        "refresh_token": os.environ.get("SPOTIFY_REFRESH_TOKEN"),
    }


# ==============================
# ---- Spotify Interaction ----
# ==============================


def fetch_recent_tracks(sp, after_timestamp=None):
    """
    Pull recently played tracks.
    Filters by last_checked timestamp if provided.
    """
    results = sp.current_user_recently_played(limit=50)

    tracks = []
    for item in results["items"]:
        played_at = item["played_at"]

        if after_timestamp and played_at <= after_timestamp:
            continue

        track = item["track"]
        album = track["album"]

        tracks.append(
            {
                "track_id": track["id"],
                "album_id": album["id"],
                "album_name": album["name"],
                "artist": ", ".join(a["name"] for a in album["artists"]),
                "played_at": played_at,
            }
        )

    return tracks


# ==============================
# ---- Album Tracking Logic ----
# ==============================


def update_album_progress(state, sp, tracks):
    """
    Updates albums_in_progress with newly played tracks.
    """

    for t in tracks:
        album_id = t["album_id"]

        if album_id not in state["albums_in_progress"]:
            # Fetch album metadata once
            album_meta = sp.album(album_id)
            total_tracks = album_meta["total_tracks"]

            state["albums_in_progress"][album_id] = {
                "album_name": t["album_name"],
                "artist": t["artist"],
                "total_tracks": total_tracks,
                "played_tracks": [],
                "first_played": t["played_at"],
                "last_played": t["played_at"],
            }

        album_entry = state["albums_in_progress"][album_id]

        if t["track_id"] not in album_entry["played_tracks"]:
            album_entry["played_tracks"].append(t["track_id"])

        album_entry["last_played"] = t["played_at"]


def check_album_completion(state):
    """
    Determine which albums meet completion criteria.

    Placeholder logic:
    - Strict: all tracks played
    """

    completed = []

    for album_id, album_data in state["albums_in_progress"].items():
        if album_id in state["completed_albums"]:
            continue

        if len(album_data["played_tracks"]) >= album_data["total_tracks"]:
            completed.append(album_id)

    return completed


def log_completed_album(state, album_id):
    """
    Placeholder logging sink.
    Later this can:
    - Append to Google Sheets
    - Send to Notion
    - Insert into DB
    """

    album_data = state["albums_in_progress"][album_id]

    print(f"Album completed: {album_data['artist']} - {album_data['album_name']}")

    state["completed_albums"][album_id] = {
        "completed_at": datetime.datetime.utcnow().isoformat(),
        "listen_count": 1,
    }


# ==============================
# ---- Main Execution ----
# ==============================


def main():
    state = load_state()

    credentials = get_local_credentials()
    spotify = SpotifyAPI(credentials)
    sp = spotify.sp

    tracks = fetch_recent_tracks(sp, state["last_checked"])

    if not tracks:
        print("No new tracks found.")
    else:
        update_album_progress(state, sp, tracks)

        completed_album_ids = check_album_completion(state)

        for album_id in completed_album_ids:
            log_completed_album(state, album_id)

        # Update last_checked
        newest_timestamp = max(t["played_at"] for t in tracks)
        state["last_checked"] = newest_timestamp

    save_state(state)


if __name__ == "__main__":
    main()
