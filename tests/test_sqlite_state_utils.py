import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import utils


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
            state_file = Path(temp_dir) / "album_state.json"

            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": database_url,
                    "STATE_FILE": str(state_file),
                },
            ):
                utils.save_state(sample_state())
                loaded = utils.load_state()

        self.assertFalse(state_file.exists())
        self.assertEqual(loaded["last_checked"], "2026-04-18T16:14:25.872Z")
        self.assertEqual(
            loaded["completed_albums"]["Artist - Album"]["listen_history"],
            ["2026-04-18T15:45:00.000Z"],
        )


if __name__ == "__main__":
    unittest.main()
