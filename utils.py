import os
import json
import datetime
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
STATE_FILE = os.environ.get("STATE_FILE")


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
