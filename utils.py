import os
import json
import datetime
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
STATE_FILE = os.environ.get("STATE_FILE")
MANUAL_ENTRY_FILE = os.environ.get("MANUAL_ENTRY_FILE")
GOOGLE_SHEETS_ENTRY_FILE = os.environ.get("GOOGLE_SHEETS_ENTRY_FILE")
SOURCE_PRIORITY_BY_PARAM = {"updated": 3, "manual": 2, "start": 1, "google_sheets": 0}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_checked": None, "albums_in_progress": {}, "completed_albums": {}}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def load_manual_entries():
    if not os.path.exists(MANUAL_ENTRY_FILE):
        return {"completed_albums": {}}

    with open(MANUAL_ENTRY_FILE, "r") as f:
        return json.load(f)


def load_google_sheets_entries():
    if not os.path.exists(GOOGLE_SHEETS_ENTRY_FILE):
        return {"completed_albums": {}}

    with open(GOOGLE_SHEETS_ENTRY_FILE, "r") as f:
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


def merge_completed_albums_with_priority(start_state, **album_dicts):
    """
    Merge additional album dicts into a starting state using source priority.

    Each kwarg name (e.g. spotify=..., discogs=...) is used to determine
    priority via SOURCE_PRIORITY_BY_PARAM.

    Stats are measured relative to the start_state.
    """

    merged = start_state.copy()

    stats = {
        "added": 0,  # new albums not in start_state
        "overwritten": 0,  # start_state entries replaced by higher priority
        "skipped_lower_priority": 0,
    }

    for param_name, album_dict in album_dicts.items():
        incoming_priority = SOURCE_PRIORITY_BY_PARAM.get(param_name, -1)

        for key, record in album_dict.items():

            if key not in merged:
                merged[key] = record
                stats["added"] += 1
                continue

            existing_record = merged[key]
            existing_source = existing_record.get("source")
            existing_priority = SOURCE_PRIORITY_BY_PARAM.get(existing_source, -1)

            if incoming_priority > existing_priority:
                print(
                    f"[OVERWRITE] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"overrode {existing_source} ({existing_priority})"
                )
                merged[key] = record
                stats["overwritten"] += 1

            elif incoming_priority == existing_priority:
                print(
                    f"[EQUAL PRIORITY] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"tied with {existing_source} ({existing_priority}) - keeping existing"
                )
                stats["skipped_lower_priority"] += 1

            else:
                print(
                    f"[SKIP] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"lost to {existing_source} ({existing_priority})"
                )
                stats["skipped_lower_priority"] += 1

    print("MERGE STATS:", stats)
    print("FINAL TOTAL:", len(merged))

    return merged
