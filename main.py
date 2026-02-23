import os
import json
import datetime
from collections import defaultdict
from dotenv import load_dotenv

from spotify_manager import SpotifyAPI
import utils as util
import tracking as tracking

load_dotenv()
THRESHOLD = 0.2


def main():
    state = util.load_state()

    credentials = util.get_local_credentials()
    spotify = SpotifyAPI(credentials)

    tracks = spotify.fetch_recent_tracks(state["last_checked"])

    tracking.update_album_progress(state, spotify, tracks)

    completed_album_ids = tracking.check_album_completion(state, threshold=THRESHOLD)

    for album_id in completed_album_ids:
        tracking.log_completed_album(state, spotify, album_id)

    # Update last_checked
    newest_timestamp = max(t["played_at"] for t in tracks)
    state["last_checked"] = newest_timestamp

    util.save_state(state)


if __name__ == "__main__":
    main()
