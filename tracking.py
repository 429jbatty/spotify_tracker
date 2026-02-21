import datetime
from spotify_manager import SpotifyAPI


def update_album_progress(state, tracks):
    """
    Updates albums_in_progress with newly played tracks.
    """

    for t in tracks:
        album_id = t["album_id"]

        if album_id not in state["albums_in_progress"]:
            # Fetch album metadata once
            album_meta = SpotifyAPI.fetch_album_metadata()
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
