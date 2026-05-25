import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Spotify Tracker API"
    api_prefix: str = "/api"
    data_dir: str = str(DEFAULT_DATA_DIR)
    database_url: str = f"sqlite:///{DEFAULT_DATA_DIR / 'spotify_tracker.sqlite'}"
    frontend_origin: str = "http://localhost:5173"
    media_dir: str = str(DEFAULT_DATA_DIR / "media")
    lastfm_api_key: str | None = None
    spotify_import_max_zip_bytes: int = 250 * 1024 * 1024
    spotify_import_max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    spotify_import_max_zip_entries: int = 200


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR", Settings.data_dir)).expanduser()
    database_url = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{data_dir / 'spotify_tracker.sqlite'}",
    )
    media_dir = os.environ.get("MEDIA_DIR", str(data_dir / "media"))

    return Settings(
        app_name=os.environ.get("APP_NAME", Settings.app_name),
        api_prefix=os.environ.get("API_PREFIX", Settings.api_prefix),
        data_dir=str(data_dir),
        database_url=database_url,
        frontend_origin=os.environ.get(
            "FRONTEND_ORIGIN",
            Settings.frontend_origin,
        ),
        media_dir=media_dir,
        lastfm_api_key=os.environ.get("LASTFM_API_KEY"),
        spotify_import_max_zip_bytes=int(
            os.environ.get(
                "SPOTIFY_IMPORT_MAX_ZIP_BYTES",
                Settings.spotify_import_max_zip_bytes,
            )
        ),
        spotify_import_max_uncompressed_bytes=int(
            os.environ.get(
                "SPOTIFY_IMPORT_MAX_UNCOMPRESSED_BYTES",
                Settings.spotify_import_max_uncompressed_bytes,
            )
        ),
        spotify_import_max_zip_entries=int(
            os.environ.get(
                "SPOTIFY_IMPORT_MAX_ZIP_ENTRIES",
                Settings.spotify_import_max_zip_entries,
            )
        ),
    )
