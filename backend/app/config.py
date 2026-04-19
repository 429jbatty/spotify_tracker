import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_STATE_FILE = ROOT_DIR / "frontend" / "public" / "album_state.json"
DEFAULT_EXPORT_FILE = ROOT_DIR / "data" / "exports" / "album_state_export.json"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Spotify Tracker API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///data/spotify_tracker.sqlite"
    frontend_origin: str = "http://localhost:5173"
    state_file: str = str(DEFAULT_STATE_FILE)
    export_state_file: str = str(DEFAULT_EXPORT_FILE)
    album_state_backend: str = "sqlite"


def get_settings() -> Settings:
    return Settings(
        app_name=os.environ.get("APP_NAME", Settings.app_name),
        api_prefix=os.environ.get("API_PREFIX", Settings.api_prefix),
        database_url=os.environ.get("DATABASE_URL", Settings.database_url),
        frontend_origin=os.environ.get(
            "FRONTEND_ORIGIN",
            Settings.frontend_origin,
        ),
        state_file=os.environ.get("STATE_FILE", Settings.state_file),
        export_state_file=os.environ.get(
            "EXPORT_STATE_FILE",
            Settings.export_state_file,
        ),
        album_state_backend=os.environ.get(
            "ALBUM_STATE_BACKEND",
            Settings.album_state_backend,
        ),
    )
