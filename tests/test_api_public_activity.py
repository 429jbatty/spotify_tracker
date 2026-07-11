import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.models import User
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.public_activity_service import _select_activity_items


class PublicActivityApiTests(unittest.TestCase):
    def _activity_candidate(self, user_slug, activity_type, score, text):
        return {
            "type": activity_type,
            "user_display_name": user_slug,
            "public_user_display_name": user_slug,
            "album_title": text,
            "artist_name": "Artist",
            "album_cover_url": None,
            "text": text,
            "timestamp": "2026-04-20T15:45:00.000Z",
            "profile_url": f"/{user_slug}",
            "_score": score,
            "_user_slug": user_slug,
        }

    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with session_factory() as session:
            UserRepository(session).create_user(
                slug="friend",
                display_name="Friend",
            )
            UserRepository(session).create_user(
                slug="smoke-test",
                display_name="smoke test",
            )
            inactive = User(slug="inactive", display_name="Inactive", is_active=False)
            session.add(inactive)
            session.commit()
            SqliteStateRepository(session).save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Artist One - Older Album": {
                            "artist": "Artist One",
                            "name": "Older Album",
                            "image_url": "https://example.com/older.jpg",
                            "source": "manual",
                            "listen_history": ["2026-04-18T15:45:00.000Z"],
                            "rating": 9,
                            "notes": "private note",
                            "your_tags": ["private-tag"],
                        },
                        "Artist One - Replay Album": {
                            "artist": "Artist One",
                            "name": "Replay Album",
                            "image_url": "https://example.com/replay.jpg",
                            "release_year": 2011,
                            "source": "manual",
                            "listen_history": [
                                "2026-04-01T15:45:00.000",
                                "2026-04-18T15:45:00.000Z",
                            ],
                        },
                    },
                    "most_recently_listened": [
                        "Artist One - Replay Album",
                        "Artist One - Older Album",
                    ],
                }
            )
            SqliteStateRepository(session, user_slug="friend").save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Artist Two - Newer Album": {
                            "artist": "Artist Two",
                            "name": "Newer Album",
                            "local_image_path": "artwork/newer.jpg",
                            "release_year": 1997,
                            "source": "manual",
                            "listen_history": ["2026-04-19T15:45:00.000Z"],
                        },
                        "Artist Three - Missing Art": {
                            "artist": "Artist Three",
                            "name": "Missing Art",
                            "release_year": 2015,
                            "source": "manual",
                            "listen_history": ["2026-04-17T15:45:00.000Z"],
                        },
                    },
                    "most_recently_listened": [
                        "Artist Two - Newer Album",
                        "Artist Three - Missing Art",
                    ],
                }
            )
            SqliteStateRepository(session, user_slug="smoke-test").save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Demo Artist - Demo Album": {
                            "artist": "Demo Artist",
                            "name": "Demo Album",
                            "image_url": "https://example.com/demo.jpg",
                            "release_year": 2021,
                            "source": "manual",
                            "listen_history": ["2026-04-16T15:45:00.000Z"],
                        },
                    },
                    "most_recently_listened": ["Demo Artist - Demo Album"],
                }
            )
            SqliteStateRepository(session, user_slug="inactive").save_album_state(
                {
                    "last_checked": None,
                    "albums_in_progress": {},
                    "completed_albums": {
                        "Hidden Artist - Hidden Album": {
                            "artist": "Hidden Artist",
                            "name": "Hidden Album",
                            "image_url": "https://example.com/hidden.jpg",
                            "source": "manual",
                            "listen_history": ["2026-04-20T15:45:00.000Z"],
                        },
                    },
                    "most_recently_listened": ["Hidden Artist - Hidden Album"],
                }
            )
            session.execute(
                text(
                    "UPDATE albums SET metadata_json = :metadata_json "
                    "WHERE name = :album_name"
                ),
                {"metadata_json": '{"broken":', "album_name": "Newer Album"},
            )
            session.commit()

        patcher = patch.dict(
            "os.environ",
            {
                "DATABASE_URL": database_url,
                "MEDIA_DIR": temp_dir,
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def test_recent_listens_returns_latest_public_album_fields_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)

            response = client.get("/api/public/recent-listens?limit=2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [
                (
                    album["listener_display_name"],
                    album["listened_at"],
                    album["artist"],
                    album["name"],
                )
                for album in payload
            ],
            [
                (
                    "Friend",
                    "2026-04-19T15:45:00.000Z",
                    "Artist Two",
                    "Newer Album",
                ),
                (
                    "Jacob",
                    "2026-04-18T15:45:00.000Z",
                    "Artist One",
                    "Replay Album",
                ),
            ],
        )
        self.assertEqual(payload[0]["image_url"], "/media/artwork/newer.jpg")
        self.assertEqual(
            set(payload[0].keys()),
            {
                "listen_id",
                "listener_display_name",
                "listened_at",
                "album_id",
                "album_key",
                "artist",
                "name",
                "image_url",
            },
        )
        self.assertFalse(
            any(album["listener_display_name"] == "Inactive" for album in payload)
        )
        self.assertNotIn("rating", payload[0])
        self.assertNotIn("notes", payload[0])
        self.assertNotIn("your_tags", payload[0])

    def test_splash_returns_public_profile_activity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)

            response = client.get("/api/public/splash")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            [user["slug"] for user in payload["featured_users"]],
            ["friend", "jacob", "smoke-test"],
        )
        friend = payload["featured_users"][0]
        self.assertEqual(friend["display_name"], "Friend")
        self.assertEqual(friend["public_display_name"], "Friend")
        self.assertEqual(friend["profile_url"], "/friend")
        self.assertEqual(friend["total_albums"], 2)
        self.assertEqual(friend["total_listens"], 2)
        self.assertEqual(friend["discovery_rate"], 1.0)
        self.assertEqual(friend["replay_rate_30d"], 0.0)
        self.assertNotIn("profile_badge", friend)
        self.assertEqual(friend["top_artist"], "Artist Two")
        self.assertEqual(friend["top_artist_listen_count"], 1)
        self.assertEqual(
            friend["top_album"],
            {"title": "Newer Album", "artist": "Artist Two", "listen_count": 1},
        )
        self.assertEqual(friend["most_listened_era"], {"label": "1990s", "listen_count": 1})
        self.assertIsNone(friend["most_replayed_recently"])
        self.assertEqual(friend["last_updated"], "2026-04-19T15:45:00.000Z")
        self.assertEqual(friend["recent_album_covers"], ["/media/artwork/newer.jpg"])

        jacob = payload["featured_users"][1]
        self.assertEqual(jacob["public_display_name"], "Jacob")
        self.assertEqual(jacob["total_albums"], 2)
        self.assertEqual(jacob["total_listens"], 3)
        self.assertEqual(jacob["discovery_rate"], 0.67)
        self.assertEqual(jacob["replay_rate_30d"], 0.5)
        self.assertNotIn("profile_badge", jacob)
        self.assertEqual(jacob["top_artist"], "Artist One")
        self.assertEqual(jacob["top_artist_listen_count"], 3)
        self.assertEqual(
            jacob["top_album"],
            {"title": "Replay Album", "artist": "Artist One", "listen_count": 2},
        )
        self.assertEqual(jacob["most_listened_era"], {"label": "2010s", "listen_count": 2})
        self.assertEqual(
            jacob["most_replayed_recently"],
            {
                "title": "Replay Album",
                "artist": "Artist One",
                "replay_count": 1,
                "window_days": 30,
            },
        )

        smoke_test = payload["featured_users"][2]
        self.assertEqual(smoke_test["display_name"], "smoke test")
        self.assertEqual(smoke_test["public_display_name"], "Demo Listener")
        self.assertNotIn("profile_badge", smoke_test)
        self.assertEqual(smoke_test["profile_url"], "/smoke-test")

        self.assertNotIn("inactive", [user["slug"] for user in payload["featured_users"]])

        activity = payload["recent_activity"]
        self.assertLessEqual(len(activity), 5)
        self.assertTrue(
            any(
                item["user_display_name"] == "Friend"
                and item["public_user_display_name"] == "Friend"
                and item["type"] == "discovery"
                and item["album_cover_url"] == "/media/artwork/newer.jpg"
                and item["profile_url"] == "/friend"
                and "Friend discovered Newer Album." in item["text"]
                for item in activity
            )
        )
        self.assertTrue(
            any(
                item["user_display_name"] == "smoke test"
                and item["public_user_display_name"] == "Demo Listener"
                and item["text"] == "Demo Listener discovered Demo Album."
                for item in activity
            )
        )
        self.assertTrue(
            any(
                item["type"] == "replay"
                and item["text"] == "Jacob replayed Replay Album after 17 days."
                for item in activity
            )
        )
        self.assertFalse(
            any(item["user_display_name"] == "Inactive" for item in activity)
        )

    def test_activity_selection_prefers_mix_and_long_gap_replays(self):
        candidates = [
            self._activity_candidate("jacob", "replay", 3.51, "latest same user 1"),
            self._activity_candidate("jacob", "replay", 3.52, "latest same user 2"),
            self._activity_candidate("jacob", "replay", 3.53, "latest same user 3"),
            self._activity_candidate("friend", "discovery", 3.0, "friend discovery"),
            self._activity_candidate("smoke-test", "replay", 4.4, "long gap replay"),
            self._activity_candidate("ben", "discovery", 3.0, "ben discovery"),
        ]

        selected = _select_activity_items(candidates, limit=5)

        self.assertIn("friend discovery", [item["text"] for item in selected])
        self.assertLessEqual(
            max_consecutive(
                [item["_user_slug"] for item in selected],
                "jacob",
            ),
            2,
        )
        self.assertEqual(selected[0]["text"], "long gap replay")

    def test_splash_handles_empty_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
            create_schema(database_url)
            patcher = patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": database_url,
                    "MEDIA_DIR": temp_dir,
                },
            )
            patcher.start()
            self.addCleanup(patcher.stop)
            client = TestClient(create_app())

            response = client.get("/api/public/splash")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["featured_users"], [])
        self.assertEqual(response.json()["recent_activity"], [])


def max_consecutive(values, target):
    longest = 0
    current = 0
    for value in values:
        if value == target:
            current += 1
        else:
            longest = max(longest, current)
            current = 0
    return max(longest, current)


if __name__ == "__main__":
    unittest.main()
