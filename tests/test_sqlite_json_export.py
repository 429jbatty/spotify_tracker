import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import utils
from one_time_scripts._export_sqlite_to_json import export_sqlite_to_json


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


class SqliteJsonExportTests(unittest.TestCase):
    def test_export_sqlite_to_json_writes_album_state_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            export_path = Path(temp_dir) / "album_state_export.json"

            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": database_url,
                    "EXPORT_STATE_FILE": str(export_path),
                },
            ):
                utils.save_state(sample_state())
                export_sqlite_to_json()

            exported = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(exported["last_checked"], "2026-04-18T16:14:25.872Z")
        self.assertEqual(
            exported["completed_albums"]["Artist - Album"]["listen_history"],
            ["2026-04-18T15:45:00.000Z"],
        )


if __name__ == "__main__":
    unittest.main()
