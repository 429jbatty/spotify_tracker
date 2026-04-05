from datetime import datetime, timezone
from spotify_manager import SpotifyAPI
import album_metadata_service as meta
import logging
from dateutil import parser

logger = logging.getLogger(__name__)

from dateutil import parser
from datetime import datetime, timezone, timedelta


def cleanup_stale_albums(state, max_age_hours=48):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    logging.info(f"Cleaning up albums not listened to since {cutoff.isoformat()}")

    to_remove = []
    for album_id, album in state["albums_in_progress"].items():
        last_played = parser.isoparse(album["last_played"])

        if last_played.tzinfo is None:
            last_played = last_played.replace(tzinfo=timezone.utc)

        if last_played < cutoff:
            to_remove.append(album_id)

    for album_id in to_remove:
        logging.info(
            f"Removing stale album from in-progress: {state['albums_in_progress'][album_id]['artist']} - {state['albums_in_progress'][album_id]['album_name']}"
        )
        del state["albums_in_progress"][album_id]

    return state


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

    if (threshold > 1) or (threshold < 0.01):
        raise ValueError("threshold must be between 0 and 1")

    completed = []

    for album_id, album_data in state["albums_in_progress"].items():

        if album_data.get("completion_logged"):
            continue

        total_tracks = album_data["total_tracks"]
        unique_tracks = album_data["played_tracks"]

        percent_listened = len(unique_tracks) / total_tracks
        if percent_listened < threshold:
            continue

        completed.append(album_id)

    return completed


def log_completed_album(state, album_id):

    # get album data
    album_logged_data = state["albums_in_progress"][album_id]
    artist = album_logged_data["artist"]
    album_name = album_logged_data["album_name"]
    album_metadata = meta.get_album_metadata(
        artist, album_name
    )  # inefficient because might not be needed
    key = f"{artist} - {album_name}"
    listen_datetime = album_logged_data["last_played"]

    if key not in state["completed_albums"]:
        album_metadata["listen_history"] = [listen_datetime]
        logging.info(f"New album logged: {artist} - {album_name}")
        entry = {key: album_metadata}

    else:
        state["completed_albums"][key].setdefault("listen_history", []).append(
            listen_datetime
        )
        logging.info(f"Subsequent listen logged: {artist} - {album_name}")
        entry = {key: state["completed_albums"][key]}

    entry[key]["completion_logged"] = True

    return entry


def get_most_recently_listened(state: dict, num=10) -> list[str]:
    albums = state.get("completed_albums", {})

    def parse_utc(ts):
        dt = parser.isoparse(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    album_to_most_recent_listen = {}
    for key, album_data in albums.items():
        try:
            history = album_data.get("listen_history", [])
            if history:
                most_recent_listen = max(parse_utc(dt) for dt in history)
                album_to_most_recent_listen[key] = most_recent_listen
        except Exception as e:
            logging.warning(f"Error parsing listen history for {key}: {e}")
            continue

    # get most recent num albums
    sorted_albums = sorted(
        album_to_most_recent_listen.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:num]

    return [key for key, _ in sorted_albums]
