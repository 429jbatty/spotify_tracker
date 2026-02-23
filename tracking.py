import datetime
from spotify_manager import SpotifyAPI


def update_album_progress(state, sp: SpotifyAPI, tracks):
    """
    Updates albums_in_progress with newly played tracks.
    """

    for t in tracks:
        album_id = t["album_id"]

        if album_id not in state["albums_in_progress"]:
            # Fetch album metadata once
            album_meta = sp.fetch_album_metadata(album_id)
            if album_meta["album_type"] != "album":
                print(f"Skipping {album_meta['name']} because it's not an album")
                continue
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


def check_album_completion(state, threshold: float):
    """
    Determine which albums meet completion criteria.

    Placeholder logic:
    - Strict: all tracks played
    """

    # verify threshold
    if (threshold > 1) or (threshold < 0.01):
        raise ValueError("threshold must be between 0 and 1")

    completed = []

    for album_id, album_data in state["albums_in_progress"].items():
        if album_id in state["completed_albums"]:
            continue

        # verify threshold met (% of songs on album)
        total_tracks = album_data["total_tracks"]
        unique_tracks = album_data["played_tracks"]

        if len(unique_tracks) / total_tracks < threshold:
            continue

        completed.append(album_id)

    return completed


def log_completed_album(state, sp: SpotifyAPI, album_id):

    # get album data
    album_logged_data = state["albums_in_progress"][album_id]
    album_metadata = sp.fetch_album_metadata(album_id)
    album_art = album_metadata["images"][0]["url"] if album_metadata["images"] else None
    print(
        f"Album completed: {album_logged_data['artist']} - {album_logged_data['album_name']}"
    )
    artist = album_metadata["artists"][0]["name"]
    metadata_variables_to_track = [
        "album_type",
        "total_tracks",
        "name",
        "release_date",
        "label",
    ]

    filtered_dict = {
        k: album_metadata[k] for k in metadata_variables_to_track if k in album_metadata
    }

    state["completed_albums"][album_id] = {
        "listen_date": album_logged_data["last_played"],
        "listen_count": 1,
        **filtered_dict,
        "image_url": album_art,
        "artist": artist,
    }
