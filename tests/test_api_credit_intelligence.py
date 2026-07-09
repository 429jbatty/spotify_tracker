import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.main import create_app
from backend.app.models import Album, AlbumCreditFact, AlbumListen, User, UserAlbum


class ApiCreditIntelligenceTests(unittest.TestCase):
    def _client(self, temp_dir):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            self._seed_fixture(session)

        patcher = patch.dict("os.environ", {"DATABASE_URL": database_url})
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app())

    def _seed_fixture(self, session):
        listener = User(slug="listener", display_name="Listener", is_active=True)
        friend = User(slug="friend", display_name="Friend", is_active=True)
        sparse = User(slug="sparse", display_name="Sparse", is_active=True)
        session.add_all([listener, friend, sparse])
        session.flush()

        album_one = self._album("artist-a-1", "Artist A", "Album One", "artist-a-mbid")
        album_one.image_url = "https://example.test/album-one.jpg"
        album_two = self._album("artist-b-2", "Artist B", "Album Two", "artist-b-mbid")
        album_three = self._album("artist-a-3", "Artist A Alias", "Album Three", "artist-a-mbid")
        album_one_duplicate = self._album(
            "artist-a-1-deluxe",
            "Artist A",
            "Album One",
            "artist-a-mbid",
        )
        album_four = self._album("artist-c-4", "Artist C", "Album Four", "artist-c-mbid")
        isolated_album = self._album("artist-e-7", "Artist E", "Isolated Album", "artist-e-mbid")
        friend_album = self._album("artist-f-6", "Artist F", "Friend Album", "artist-f-mbid")
        sparse_album = self._album("artist-d-5", "Artist D", "Sparse Album", "artist-d-mbid")
        session.add_all(
            [
                album_one,
                album_two,
                album_three,
                album_one_duplicate,
                album_four,
                isolated_album,
                friend_album,
                sparse_album,
            ]
        )
        session.flush()

        for album in [album_one, album_two, album_three, album_one_duplicate, album_four, isolated_album]:
            session.add(UserAlbum(user_id=listener.id, album_id=album.id))
        session.add(UserAlbum(user_id=friend.id, album_id=friend_album.id))
        session.add(UserAlbum(user_id=sparse.id, album_id=sparse_album.id))

        long_bridge_album = self._album(
            "artist-g-9",
            "Artist G",
            "Long Bridge Album",
            "artist-g-mbid",
        )
        long_target_album = self._album(
            "artist-h-10",
            "Artist H",
            "Long Target Album",
            "artist-h-mbid",
        )
        session.add_all([long_bridge_album, long_target_album])
        session.flush()
        session.add(UserAlbum(user_id=listener.id, album_id=long_bridge_album.id))
        session.add(UserAlbum(user_id=listener.id, album_id=long_target_album.id))

        session.add_all(
            [
                AlbumListen(
                    user_id=listener.id,
                    album_id=album_one.id,
                    listened_at="2026-01-01T00:00:00Z",
                    source="test",
                ),
                AlbumListen(
                    user_id=listener.id,
                    album_id=album_one.id,
                    listened_at="2026-01-02T00:00:00Z",
                    source="test",
                ),
                AlbumListen(
                    user_id=listener.id,
                    album_id=album_two.id,
                    listened_at="2026-01-03T00:00:00Z",
                    source="test",
                ),
                AlbumListen(
                    user_id=friend.id,
                    album_id=friend_album.id,
                    listened_at="2026-01-04T00:00:00Z",
                    source="test",
                ),
            ]
        )

        session.add_all(
            [
                self._fact(album_one, "mbid:producer-1", "Producer One", "producer-1", "producer"),
                self._fact(album_two, "mbid:producer-1", "Producer One", "producer-1", "producer"),
                self._fact(album_three, "mbid:producer-1", "Producer One", "producer-1", "producer"),
                self._fact(
                    album_one,
                    "name:writer one",
                    "Writer One",
                    None,
                    "writer_composer",
                    identity_resolution="normalized_name",
                    flags=["legacy_credit", "name_only_identity"],
                ),
                self._fact(
                    album_two,
                    "name:writer one",
                    "Writer One",
                    None,
                    "writer_composer",
                    identity_resolution="normalized_name",
                    flags=["legacy_credit", "name_only_identity"],
                ),
                self._fact(
                    album_one,
                    "name:artist a",
                    "Artist A",
                    None,
                    "other",
                    flags=["primary_artist_candidate"],
                ),
                self._fact(
                    album_one,
                    "name:instrument person",
                    "Instrument Person",
                    None,
                    "other",
                    flags=["generic_instrument"],
                ),
                self._fact(
                    album_one,
                    "unresolved:mystery",
                    "Mystery",
                    None,
                    "producer",
                    identity_resolution="unresolved",
                    flags=["unresolved_identity"],
                ),
                self._fact(
                    album_one,
                    "name:same artist member",
                    "Same Artist Member",
                    None,
                    "writer_composer",
                ),
                self._fact(
                    album_three,
                    "name:same artist member",
                    "Same Artist Member",
                    None,
                    "writer_composer",
                ),
                self._fact(
                    album_one,
                    "name:[traditional]",
                    "[traditional]",
                    None,
                    "writer_composer",
                ),
                self._fact(
                    album_two,
                    "name:[traditional]",
                    "[traditional]",
                    None,
                    "writer_composer",
                ),
                self._fact(
                    album_one,
                    "mbid:duplicate-producer",
                    "Duplicate Producer",
                    "duplicate-producer",
                    "producer",
                ),
                self._fact(
                    album_one_duplicate,
                    "mbid:duplicate-producer",
                    "Duplicate Producer",
                    "duplicate-producer",
                    "producer",
                ),
                self._fact(
                    album_one,
                    "mbid:weak-link",
                    "Weak Link",
                    "weak-link",
                    "producer",
                    flags=["enriched_credit", "single_track_credit"],
                    track_count=1,
                ),
                self._fact(
                    album_three,
                    "mbid:bridge-engineer",
                    "Bridge Engineer",
                    "bridge-engineer",
                    "engineering",
                ),
                self._fact(
                    album_four,
                    "mbid:bridge-engineer",
                    "Bridge Engineer",
                    "bridge-engineer",
                    "engineering",
                ),
                self._fact(
                    album_three,
                    "mbid:weak-link",
                    "Weak Link",
                    "weak-link",
                    "producer",
                    flags=["enriched_credit", "single_track_credit"],
                    track_count=1,
                ),
                self._fact(
                    isolated_album,
                    "mbid:isolated-person",
                    "Isolated Person",
                    "isolated-person",
                    "producer",
                ),
                self._fact(
                    album_four,
                    "mbid:long-connector",
                    "Long Connector",
                    "long-connector",
                    "mixing_mastering",
                    flags=["enriched_credit", "single_track_credit"],
                    track_count=1,
                ),
                self._fact(
                    long_bridge_album,
                    "mbid:long-connector",
                    "Long Connector",
                    "long-connector",
                    "mixing_mastering",
                    flags=["enriched_credit", "single_track_credit"],
                    track_count=1,
                ),
                self._fact(
                    long_bridge_album,
                    "mbid:final-connector",
                    "Final Connector",
                    "final-connector",
                    "engineering",
                ),
                self._fact(
                    long_target_album,
                    "mbid:final-connector",
                    "Final Connector",
                    "final-connector",
                    "engineering",
                ),
                self._fact(friend_album, "mbid:producer-1", "Producer One", "producer-1", "producer"),
            ]
        )
        session.commit()

    def _album(self, key, artist, name, artist_mbid):
        return Album(
            album_key=key,
            artist=artist,
            name=name,
            artist_mbid=artist_mbid,
            source="musicbrainz",
            entry_source="spotify_sync",
            metadata_json={},
        )

    def _fact(
        self,
        album,
        person_key,
        person_name,
        person_mbid,
        role_bucket,
        *,
        identity_resolution="mbid",
        flags=None,
        track_count=2,
    ):
        return AlbumCreditFact(
            album_id=album.id,
            person_key=person_key,
            person_name=person_name,
            person_mbid=person_mbid,
            identity_resolution=identity_resolution,
            ingestion_version=(
                "musicbrainz_credit_v2"
                if identity_resolution == "mbid"
                else "legacy_tuple_credit_v1"
            ),
            raw_role="producer" if role_bucket == "producer" else "work writer",
            role_bucket=role_bucket,
            source_scope="recording",
            recording_mbid=None,
            track_count=track_count,
            album_track_count=10,
            track_share=track_count / 10,
            quality_flags_json=flags or ["enriched_credit"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )

    def test_recurring_contributors_returns_ranked_user_scoped_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/listener/connections/recurring")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_slug"], "listener")
        self.assertEqual(payload["coverage"]["library_album_count"], 8)
        self.assertEqual(payload["coverage"]["albums_with_facts"], 8)

        names = [item["person_name"] for item in payload["results"]]
        self.assertEqual(names[0], "Producer One")
        self.assertIn("Writer One", names)
        self.assertIn("Bridge Engineer", names)
        self.assertNotIn("Artist A", names)
        self.assertNotIn("Instrument Person", names)
        self.assertNotIn("Mystery", names)
        self.assertNotIn("Same Artist Member", names)
        self.assertNotIn("[traditional]", names)

        producer = payload["results"][0]
        self.assertEqual(producer["connected_album_count"], 3)
        self.assertEqual(producer["distinct_primary_artist_count"], 2)
        self.assertNotIn("total_listen_count", producer)
        self.assertNotIn("listen_count", producer["representative_albums"][0])
        self.assertEqual(producer["role_buckets"], {"producer": 3})
        self.assertEqual(
            [album["name"] for album in producer["representative_albums"]],
            ["Album One", "Album Three", "Album Two"],
        )

    def test_album_pairs_return_traceable_direct_connections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/listener/connections/album-pairs?limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_slug"], "listener")
        self.assertIsNone(payload["insufficient_data_reason"])

        results = payload["results"]
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertEqual(first["contributor"]["person_name"], "Producer One")
        self.assertEqual(first["contributor"]["role_bucket"], "producer")
        self.assertTrue(first["cross_primary_artist"])
        self.assertEqual(first["evidence_track_count"], 4)
        self.assertIn(first["album_a"]["name"], {"Album One", "Album Two", "Album Three"})
        self.assertIn(first["album_b"]["name"], {"Album One", "Album Two", "Album Three"})

        pair_people = [item["contributor"]["person_name"] for item in results]
        self.assertNotIn("Duplicate Producer", pair_people)
        self.assertIn("Weak Link", pair_people)
        self.assertNotIn("[traditional]", pair_people)
        self.assertNotIn("Friend Album", [item["album_a"]["name"] for item in results])
        self.assertNotIn("Friend Album", [item["album_b"]["name"] for item in results])
        self.assertTrue(all(item["album_a"]["album_id"] != item["album_b"]["album_id"] for item in results))

    def test_album_pairs_are_empty_for_sparse_credit_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/sparse/connections/album-pairs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(
            payload["insufficient_data_reason"],
            "no_projected_credit_facts",
        )

    def test_connection_graph_returns_direct_nodes_edges_and_artwork(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/graph"
                "?contributor_limit=2&album_limit_per_contributor=2&album_limit=5"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_slug"], "listener")
        self.assertEqual(payload["coverage"]["library_album_count"], 8)
        self.assertGreaterEqual(len(payload["nodes"]), 3)
        self.assertGreaterEqual(len(payload["edges"]), 2)

        contributor_nodes = [node for node in payload["nodes"] if node["type"] == "contributor"]
        album_nodes = [node for node in payload["nodes"] if node["type"] == "album"]
        self.assertTrue(any(node["label"] == "Producer One" for node in contributor_nodes))
        self.assertTrue(any(node["label"] == "Album One" for node in album_nodes))
        album_one_node = next(node for node in album_nodes if node["label"] == "Album One")
        self.assertEqual(album_one_node["image_url"], "https://example.test/album-one.jpg")
        self.assertNotIn("listen_count", album_one_node)
        self.assertNotIn("total_listen_count", contributor_nodes[0])

        edge = payload["edges"][0]
        self.assertTrue(edge["source"].startswith("contributor:"))
        self.assertTrue(edge["target"].startswith("album:"))
        self.assertIn(edge["role_bucket"], {"producer", "writer_composer"})
        self.assertNotIn("Friend Album", [node["label"] for node in album_nodes])

    def test_connection_graph_can_focus_contributor_neighborhood(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            focus_id = quote("contributor:name:writer one", safe="")
            response = client.get(
                "/api/users/listener/connections/graph"
                f"?contributor_limit=1&album_limit_per_contributor=5&album_limit=10&focus_node_id={focus_id}"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        contributor_nodes = [node for node in payload["nodes"] if node["type"] == "contributor"]
        album_nodes = [node for node in payload["nodes"] if node["type"] == "album"]

        self.assertEqual([node["label"] for node in contributor_nodes], ["Writer One"])
        self.assertEqual(
            {node["label"] for node in album_nodes},
            {"Album One", "Album Two"},
        )
        self.assertTrue(
            all(edge["source"] == "contributor:name:writer one" for edge in payload["edges"])
        )
        self.assertNotIn("Friend Album", [node["label"] for node in album_nodes])

    def test_album_connection_graph_returns_direct_shared_contributors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=1&album_b_id=2"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["album_a"]["name"], "Album One")
        self.assertEqual(payload["album_b"]["name"], "Album Two")
        self.assertFalse(payload["no_direct_connection"])
        self.assertFalse(payload["no_path"])
        self.assertEqual(payload["best_path"]["hop_count"], 1)

        people = [item["person_name"] for item in payload["shared_contributors"]]
        self.assertEqual(people, ["Producer One", "Writer One"])
        self.assertNotIn("[traditional]", people)
        self.assertNotIn("Weak Link", people)

        nodes = payload["nodes"]
        edges = payload["edges"]
        self.assertEqual({node["label"] for node in nodes if node["type"] == "album"}, {"Album One", "Album Two"})
        self.assertEqual({node["label"] for node in nodes if node["type"] == "contributor"}, {"Producer One", "Writer One"})
        self.assertEqual(len(edges), 4)
        self.assertNotIn("listen_count", nodes[0])

    def test_album_connection_graph_includes_single_track_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=1&album_b_id=3"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        people = [item["person_name"] for item in payload["shared_contributors"]]
        self.assertIn("Weak Link", people)
        weak_link = next(item for item in payload["shared_contributors"] if item["person_name"] == "Weak Link")
        self.assertIn("single_track_credit", weak_link["quality_flags"])

    def test_album_connection_graph_returns_bounded_indirect_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=2&album_b_id=5"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["no_direct_connection"])
        self.assertFalse(payload["no_path"])
        self.assertEqual(payload["best_path"]["hop_count"], 2)
        self.assertEqual(
            [step["contributor"]["person_name"] for step in payload["best_path"]["steps"]],
            ["Producer One", "Bridge Engineer"],
        )
        self.assertEqual(
            [step["contributor"]["role_bucket"] for step in payload["best_path"]["steps"]],
            ["producer", "engineering"],
        )
        self.assertIn("Album Three", {node["label"] for node in payload["nodes"]})
        self.assertIn("Bridge Engineer", {node["label"] for node in payload["nodes"]})
        self.assertEqual(payload["max_contributor_hops"], 4)

    def test_album_connection_graph_returns_four_hop_path_with_single_track_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=2&album_b_id=10"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["no_path"])
        self.assertEqual(payload["best_path"]["hop_count"], 4)
        self.assertEqual(
            [step["contributor"]["person_name"] for step in payload["best_path"]["steps"]],
            ["Producer One", "Bridge Engineer", "Long Connector", "Final Connector"],
        )
        single_track_step = payload["best_path"]["steps"][2]
        self.assertIn("single_track_credit", single_track_step["contributor"]["quality_flags"])

    def test_album_connection_graph_handles_no_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=2&album_b_id=6"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["no_direct_connection"])
        self.assertTrue(payload["no_path"])
        self.assertIsNone(payload["best_path"])
        self.assertEqual(payload["shared_contributors"], [])
        self.assertEqual({node["label"] for node in payload["nodes"]}, {"Album Two", "Isolated Album"})
        self.assertEqual(payload["edges"], [])

    def test_album_connection_graph_is_user_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/friend/connections/album-connection?album_a_id=1&album_b_id=7"
            )

        self.assertEqual(response.status_code, 404)

    def test_album_connection_graph_rejects_same_album(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get(
                "/api/users/listener/connections/album-connection?album_a_id=1&album_b_id=1"
            )

        self.assertEqual(response.status_code, 400)

    def test_person_detail_is_limited_to_current_user_library(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            person_key = quote("mbid:producer-1", safe="")
            response = client.get(
                f"/api/users/listener/connections/people/{person_key}"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["person_name"], "Producer One")
        self.assertEqual(payload["connected_album_count"], 3)
        self.assertEqual({album["artist"] for album in payload["albums"]}, {"Artist A", "Artist B", "Artist A Alias"})
        self.assertNotIn("Friend Album", [album["name"] for album in payload["albums"]])

    def test_same_database_two_users_do_not_leak_credit_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/friend/connections/recurring")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(
            payload["insufficient_data_reason"],
            "low_credit_fact_coverage",
        )

    def test_sparse_user_gets_insufficient_data_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/sparse/connections/recurring")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(
            payload["insufficient_data_reason"],
            "no_projected_credit_facts",
        )

    def test_missing_person_detail_returns_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = self._client(temp_dir)
            response = client.get("/api/users/listener/connections/people/name:missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
