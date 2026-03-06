import datetime
from spotify_manager import SpotifyAPI
import album_metadata_service as meta
import logging

logger = logging.getLogger(__name__)


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

        if t["track_spid"] not in album_entry["played_tracks"]:
            album_entry["played_tracks"].append(t["track_spid"])

        album_entry["last_played"] = t["played_at"]

    return state


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


def log_completed_album(state, album_id):

    # get album data
    album_logged_data = state["albums_in_progress"][album_id]
    artist = album_logged_data["artist"]
    album_name = album_logged_data["album_name"]
    album_metadata = meta.get_album_metadata(artist, album_name)

    key = album_metadata["release_group_mbid"]

    state["completed_albums"][key] = album_metadata

    logging.info(f"Logged completed album: {artist} - {album_name}")

    return state
