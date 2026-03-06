import os
import json
import datetime
from collections import defaultdict
from dotenv import load_dotenv

from spotify_manager import SpotifyAPI
import utils as util
import tracking as tracking
import logging


load_dotenv()
THRESHOLD = 0.90
LOG_LEVEL = logging.INFO

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logging.getLogger("musicbrainzngs").setLevel(
    logging.WARNING
)  # do not use musicbrainz info logs


def main():
    logging.info("=== Album tracking run started ===")

    start_state = util.load_state()
    starting_completed_count = len(start_state.get("completed_albums", {}))
    logging.info(f"Starting completed albums: {starting_completed_count}")

    credentials = util.get_local_credentials()
    spotify = SpotifyAPI(credentials)

    tracks = spotify.fetch_recent_tracks(start_state["last_checked"])
    logging.info(f"Fetched {len(tracks)} recent tracks from Spotify")

    updated_tracks_state = tracking.update_album_progress(start_state, spotify, tracks)

    completed_album_ids = tracking.check_album_completion(
        updated_tracks_state, threshold=THRESHOLD
    )

    spotify_new_count = len(completed_album_ids)
    logging.info(f"Newly completed albums from Spotify: {spotify_new_count}")

    updated_albums_state = updated_tracks_state

    for album_id in completed_album_ids:
        updated_albums_state = tracking.log_completed_album(
            updated_albums_state, album_id
        )

    # Update last_checked
    if tracks:
        newest_timestamp = max(t["played_at"] for t in tracks)
        updated_albums_state["last_checked"] = newest_timestamp

    # Manual + Google Sheets
    manual_entries = util.load_manual_entries()
    google_sheets_entries = util.load_google_sheets_entries()

    manual_count = len(manual_entries.get("completed_albums", {}))
    sheets_count = len(google_sheets_entries.get("completed_albums", {}))

    logging.info(f"Manual completed albums loaded: {manual_count}")
    logging.info(f"Google Sheets completed albums loaded: {sheets_count}")

    # Merge with priority logic
    end_state = updated_albums_state.copy()

    end_state["completed_albums"] = util.merge_completed_albums_with_priority(
        manual_entries["completed_albums"],
        google_sheets_entries["completed_albums"],
        updated_albums_state["completed_albums"],
    )

    final_completed_count = len(end_state["completed_albums"])
    logging.info(f"Final completed albums after merge: {final_completed_count}")

    net_change = final_completed_count - starting_completed_count
    logging.info(f"Net change this run: {net_change}")

    util.save_state(end_state)

    logging.info("=== Album tracking run completed ===")


if __name__ == "__main__":
    main()
