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
THRESHOLD = 0.9
LOG_LEVEL = logging.INFO
STALE_HOURS = 48
pull_bulk_google_sheets_data = False

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

    # delete stale listens
    clean_up_state = tracking.cleanup_stale_albums(
        start_state, max_age_hours=STALE_HOURS
    )

    # update new listens
    updated_tracks_state = tracking.update_album_progress(
        clean_up_state, spotify, tracks
    )

    # check completed albums
    completed_album_ids = tracking.check_album_completion(
        updated_tracks_state, threshold=THRESHOLD
    )

    spotify_new_count = len(completed_album_ids)
    logging.info(f"Newly completed albums from Spotify: {spotify_new_count}")

    # For all completed albums, log them and mark as logged in the state to prevent double logging on subsequent runs
    newly_completed_albums = {}
    for album_id in completed_album_ids:
        # handles both initial and subsequent completions
        new_entry = tracking.log_completed_album(updated_tracks_state, album_id)
        updated_tracks_state["albums_in_progress"][album_id]["completion_logged"] = True
        newly_completed_albums = {**newly_completed_albums, **new_entry}

    # create new object with no completed albums but timestamp and all recent tracks
    base_state = updated_tracks_state.copy()
    base_state["completed_albums"] = {}

    # Update last_checked
    if tracks:
        newest_timestamp = max(t["played_at"] for t in tracks)
        base_state["last_checked"] = newest_timestamp

    # Manual + Google Sheets
    if pull_bulk_google_sheets_data:
        google_sheets_entries = util.load_google_sheets_entries()
        sheets_count = len(google_sheets_entries.get("completed_albums", {}))
        logging.info(f"Google Sheets completed albums loaded: {sheets_count}")
    else:
        google_sheets_entries = {"completed_albums": {}}
        logging.info("Skipping Google Sheets data pull")  # log skipping

    manual_entries = util.load_manual_entries()
    manual_count = len(manual_entries.get("completed_albums", {}))
    logging.info(f"Manual completed albums loaded: {manual_count}")

    # Merge with priority logic
    end_state = base_state.copy()

    end_state["completed_albums"] = util.merge_completed_albums_with_priority(
        start_state=start_state.get("completed_albums", {}),  # start state
        manual=manual_entries["completed_albums"],
        google_sheets=google_sheets_entries["completed_albums"],
        updated=newly_completed_albums,
    )

    final_completed_count = len(end_state["completed_albums"])
    logging.info(f"Final completed albums after merge: {final_completed_count}")

    net_change = final_completed_count - starting_completed_count
    logging.info(f"Net change this run: {net_change}")

    # update most recently listened
    end_state["most_recently_listened"] = tracking.get_most_recently_listened(
        end_state, num=10
    )

    util.save_state(end_state)

    logging.info("=== Album tracking run completed ===")


if __name__ == "__main__":
    main()
