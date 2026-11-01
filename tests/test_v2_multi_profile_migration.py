import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.database import create_schema
from tests.v2_upgrade_fixture import create_v2_database


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return {
            "albums": connection.execute(
                "SELECT id, album_key, metadata_json FROM albums ORDER BY id"
            ).fetchall(),
            "memberships": connection.execute(
                "SELECT user_id, album_id, your_tags, rating, notes "
                "FROM user_albums ORDER BY user_id, album_id"
            ).fetchall(),
            "listens": connection.execute(
                "SELECT user_id, album_id, listened_at, source FROM album_listens "
                "ORDER BY user_id, listened_at, album_id"
            ).fetchall(),
            "imports": connection.execute(
                "SELECT user_id, album_id, artist, album, raw_payload "
                "FROM imported_listening_events ORDER BY id"
            ).fetchall(),
            "credits": connection.execute(
                "SELECT album_id, person_name FROM album_credit_facts ORDER BY id"
            ).fetchall(),
        }


class V2MultiProfileMigrationTests(unittest.TestCase):
    def _prepare(self, path, *, layout, partial, identity):
        create_v2_database(path, partially_migrated=partial)
        with sqlite3.connect(path) as connection:
            if layout == "separate":
                connection.executescript(
                    """
                    DELETE FROM user_albums WHERE id = 3;
                    UPDATE user_albums SET user_id = 2 WHERE album_id = 2;
                    UPDATE album_listens SET user_id = 2 WHERE album_id = 2;
                    UPDATE album_listens SET album_id = 2 WHERE user_id = 2;
                    UPDATE imported_listening_events SET user_id = 2;
                    """
                )
            elif layout == "nondefault":
                connection.executescript(
                    """
                    DELETE FROM user_albums WHERE id = 1;
                    UPDATE user_albums SET user_id = 2 WHERE album_id = 2;
                    UPDATE album_listens SET user_id = 2;
                    UPDATE imported_listening_events SET user_id = 2;
                    """
                )
            elif layout == "shared":
                connection.executescript(
                    """
                    INSERT INTO user_albums (user_id, album_id, your_tags, rating, notes)
                    VALUES (2, 2, '["cohesive"]', 5, 'Second source note');
                    INSERT INTO album_listens (user_id, album_id, listened_at, source)
                    VALUES
                        (2, 2, '2026-01-01T10:00:00Z', 'lastfm'),
                        (2, 2, '2026-01-03T10:00:00Z', 'lastfm'),
                        (2, 2, '2026-01-04T10:00:00Z', 'lastfm');
                    """
                )
            if identity != "text":
                connection.execute("UPDATE albums SET release_group_mbid = 'same-mbid'")
            if identity == "mbid":
                connection.execute("UPDATE albums SET artist = 'Alias' WHERE id = 2")
            connection.execute(
                "UPDATE albums SET metadata_json = ?, local_image_path = ? WHERE id = 2",
                (json.dumps({"tracklist": [{"title": "Track", "position": "1",
                    "credits": [["Casey Example", "producer", ""]]}]}), "artwork/cover.jpg"),
            )

    def _assert_merged(self, path, *, layout):
        state = snapshot(path)
        self.assertEqual([row[:2] for row in state["albums"]], [(1, "Artist - Album")])
        memberships = [(user, album, json.loads(tags), rating, notes)
                       for user, album, tags, rating, notes in state["memberships"]]
        if layout == "separate":
            self.assertEqual(memberships, [
                (1, 1, ["atmospheric"], None, None),
                (2, 1, ["lush"], 4, "Original note"),
            ])
            self.assertEqual([row[0] for row in state["listens"]], [1, 2, 2])
        elif layout == "nondefault":
            self.assertEqual(memberships, [
                (2, 1, ["raw", "lush"], 2, "Other note\n\nOriginal note"),
            ])
            self.assertEqual([row[0] for row in state["listens"]], [2, 2, 2])
        else:
            self.assertEqual(memberships, [
                (1, 1, ["atmospheric", "lush"], 4, "Original note"),
                (2, 1, ["raw", "cohesive"], 2, "Other note\n\nSecond source note"),
            ])
            self.assertEqual([row[0] for row in state["listens"]], [1, 1, 2, 2, 2])
            self.assertIn((2, 1, "2026-01-01T10:00:00Z", "lastfm"), state["listens"])
            self.assertIn((2, 1, "2026-01-03T10:00:00Z", "manual"), state["listens"])
            self.assertIn((2, 1, "2026-01-04T10:00:00Z", "lastfm"), state["listens"])
        self.assertTrue(all(row[1] == 1 for row in state["listens"]))
        expected_import_user = 1 if layout == "shared" else 2
        self.assertEqual(state["imports"], [(expected_import_user, 1, "artist", "album", "{}")])
        self.assertEqual(state["credits"], [(1, "Casey Example")])
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))
            self.assertEqual(connection.execute(
                "SELECT local_image_path FROM albums"
            ).fetchone(), ("artwork/cover.jpg",))
        return state

    def test_all_profile_ownership_arrangements_upgrade_and_repeat(self):
        for layout in ("separate", "shared", "nondefault"):
            for partial in (False, True):
                for identity in ("text", "same-text-and-mbid", "mbid"):
                    with self.subTest(layout=layout, partial=partial, identity=identity):
                        with tempfile.TemporaryDirectory() as directory:
                            path = Path(directory) / "v2.sqlite"
                            self._prepare(path, layout=layout, partial=partial, identity=identity)
                            url = f"sqlite:///{path}"
                            create_schema(url).dispose()
                            state = self._assert_merged(path, layout=layout)
                            create_schema(url).dispose()
                            self.assertEqual(snapshot(path), state)

    def test_credit_rebuild_failure_rolls_back_all_canonical_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.sqlite"
            self._prepare(path, layout="shared", partial=True, identity="mbid")
            before = snapshot(path)
            with patch(
                "backend.app.repositories.album_identity_migration.rebuild_credit_facts",
                side_effect=RuntimeError("synthetic projection failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic projection failure"):
                    create_schema(f"sqlite:///{path}")
            self.assertEqual(snapshot(path), before)
            # The earlier ownership migration intentionally commits separately.
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute(
                    "SELECT count(*) FROM user_spotify_credentials"
                ).fetchone(), (0,))

    def test_filling_missing_mbid_does_not_merge_conflicting_release_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.sqlite"
            create_v2_database(path, partially_migrated=True)
            with sqlite3.connect(path) as connection:
                connection.executescript(
                    """
                    UPDATE albums SET release_group_mbid = 'first-group' WHERE id = 2;
                    INSERT INTO albums (
                        id, album_key, artist, name, release_group_mbid,
                        source, entry_source, metadata_json
                    ) VALUES (
                        3, 'artist - album [different]', 'Artist', 'Album',
                        'different-group', 'manual', 'manual', '{}'
                    );
                    INSERT INTO user_albums (user_id, album_id, your_tags)
                    VALUES (2, 3, '[]');
                    """
                )
            create_schema(f"sqlite:///{path}").dispose()
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute(
                    "SELECT id, release_group_mbid FROM albums ORDER BY id"
                ).fetchall(), [(1, 'first-group'), (3, 'different-group')])
