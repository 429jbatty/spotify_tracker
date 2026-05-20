import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import utils
from backend.app.config import get_settings
from backend.app.database import create_schema


def sample_state():
    return {
        "last_checked": "2026-04-18T16:14:25.872Z",
        "albums_in_progress": {},
        "completed_albums": {
            "Artist - Album": {
                "artist": "Artist",
                "name": "Album",
                "source": "musicbrainz",
                "listen_history": ["2026-04-18T15:45:00.000Z"],
            }
        },
        "most_recently_listened": ["Artist - Album"],
    }


class SqliteStateUtilsTests(unittest.TestCase):
    def test_load_and_save_state_use_sqlite_when_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"

            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": database_url,
                },
            ):
                utils.save_state(sample_state())
                loaded = utils.load_state()

        self.assertEqual(loaded["last_checked"], "2026-04-18T16:14:25.872Z")
        self.assertEqual(
            loaded["completed_albums"]["Artist - Album"]["listen_history"],
            ["2026-04-18T15:45:00.000Z"],
        )

    def test_data_dir_controls_default_database_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "external-data"
            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}, clear=False):
                settings = get_settings()
                create_schema(settings.database_url)

                self.assertEqual(settings.data_dir, str(data_dir))
                self.assertEqual(
                    settings.database_url,
                    f"sqlite:///{data_dir / 'spotify_tracker.sqlite'}",
                )
                self.assertTrue((data_dir / "spotify_tracker.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
