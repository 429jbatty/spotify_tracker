import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database.models import Album, AlbumCreditFact, AlbumListen, ImportedListeningEvent, ImportSession, UserAlbum
from backend.app.database.repositories import import_event_repository, import_session_repository
from backend.app.database.repositories.album_catalog import AlbumCatalog
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.services.imports import candidate_results
from backend.app.services.imports.history import delete_import_session
from backend.app.services.imports.matching import AlbumCandidate
from backend.app.services.imports.metadata import load_existing_albums
from tests.database_helpers import create_schema


class AlbumRepositoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enter_directory()
        self.engine = create_schema(f"sqlite:///{directory / 'tracker.sqlite'}")
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)

    def enter_directory(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def limit_sqlite_variables(self, session, limit):
        connection = session.connection()
        driver = connection.connection.driver_connection
        if hasattr(driver, "setlimit"):
            driver.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, limit)
            return

        # Python 3.10 exposes no way to lower the driver's variable limit.
        def enforce_limit(_connection, _cursor, _statement, parameters, _context, executemany):
            bindings = parameters[0] if executemany else parameters
            if len(bindings) > limit:
                raise sqlite3.OperationalError("too many SQL variables")

        event.listen(connection, "before_cursor_execute", enforce_limit)

    def test_shared_lookup_keeps_exact_and_normalized_slug_contracts(self):
        with self.sessions() as session:
            users = UserRepository(session)
            user = users.create_user(slug=" Listening Friend ", display_name="Listening Friend")
            self.assertIs(users.find_by_slug("listening-friend"), user)
            self.assertIsNone(users.find_by_slug(" Listening Friend "))
            self.assertIs(users.get_user_by_slug(" Listening Friend "), user)

    def test_empty_artwork_scope_uses_missing_art_filter(self):
        with self.sessions() as session:
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            complete = library.add_album({
                "artist": "Artist", "name": "Complete", "release_mbid": "release-a",
                "image_url": "https://example.test/complete.jpg",
            }).record
            missing = library.add_album({
                "artist": "Artist", "name": "Missing", "release_mbid": "release-b",
            }).record
            unidentified = library.add_album({"artist": "Artist", "name": "Unidentified"}).record
            catalog = AlbumCatalog(session)

            self.assertEqual(
                [row["id"] for row in catalog.artwork_inventory()],
                [complete["id"], missing["id"], unidentified["id"]],
            )
            self.assertEqual(catalog.artwork_backfill_candidates(), catalog.artwork_backfill_candidates(ids=[]))
            self.assertEqual([row["id"] for row in catalog.artwork_backfill_candidates(ids=[])], [missing["id"]])
            self.assertEqual(
                [row["id"] for row in catalog.artwork_backfill_candidates(ids=[unidentified["id"], complete["id"]])],
                [complete["id"], unidentified["id"]],
            )

    def test_key_refresh_can_update_an_album_outside_the_maintenance_profile(self):
        with self.sessions() as session:
            users = UserRepository(session)
            owner = users.create_user(slug="owner", display_name="Owner")
            timestamp = "2026-01-01T00:00:00Z"
            created = AlbumLibrary(session, owner).add_album(
                {"artist": "Artist", "name": "Original"}, listen_date=timestamp,
            ).record
            default_user = users.ensure_default_user()
            default_library = AlbumLibrary(session, default_user)

            with self.assertRaisesRegex(KeyError, "Album is not available for user"):
                default_library.replace_metadata(created["id"], {"artist": "Artist", "name": "Renamed"})
            with patch.object(session, "commit", wraps=session.commit) as commit:
                key = default_library.replace_catalog_metadata_for_refresh(
                    created["album_key"],
                    {"artist": "Artist", "name": "Renamed", "source": "musicbrainz"},
                )
            commit.assert_called_once_with()
            self.assertEqual(key, "Artist - Renamed")

        with self.sessions() as session:
            users = UserRepository(session)
            self.assertEqual(AlbumLibrary(session, users.ensure_default_user()).list_records(), {})
            record = AlbumLibrary(session, users.require_user_by_slug("owner")).list_records()[key]
            self.assertEqual(record["id"], created["id"])
            self.assertEqual(record["listen_history"], [timestamp])

    def test_key_refresh_stages_target_credits_before_scoped_merge_checks(self):
        with self.sessions() as session:
            users = UserRepository(session)
            library = AlbumLibrary(session, users.ensure_default_user())
            other_library = AlbumLibrary(session, users.create_user(slug="other", display_name="Other"))
            source = library.add_album({"artist": "Artist", "name": "Source"}).record
            target = other_library.add_album({
                "artist": "Artist", "name": "Target", "release_group_mbid": "target-group",
                "tracklist": [{"title": "Original", "credits": [["Original Producer", "producer"]]}],
            }).record
            refreshed = {
                "artist": "Artist", "name": "Target", "release_group_mbid": "target-group",
                "tracklist": [{"title": "Refreshed", "credits": [["New Producer", "producer"]]}],
            }
            contributor = select(AlbumCreditFact.person_name).where(AlbumCreditFact.album_id == target["id"])

            with patch.object(session, "commit", wraps=session.commit) as commit:
                with self.assertRaisesRegex(KeyError, "Album is not available for user"):
                    library.replace_metadata(source["id"], refreshed)
                self.assertEqual(session.scalars(contributor).one(), "Original Producer")
                with self.assertRaisesRegex(KeyError, "Album is not available for user"):
                    library.replace_catalog_metadata_for_refresh(source["album_key"], refreshed)
                self.assertEqual(session.scalars(contributor).one(), "New Producer")
            commit.assert_not_called()
            session.rollback()

        with self.sessions() as session:
            self.assertEqual(session.scalars(contributor).one(), "Original Producer")
            self.assertEqual(session.get(Album, source["id"]).album_key, source["album_key"])

    def test_key_refresh_commits_a_scoped_merge_and_its_credit_facts_together(self):
        with self.sessions() as session:
            user = UserRepository(session).ensure_default_user()
            library = AlbumLibrary(session, user)
            source = library.add_album(
                {"artist": "Artist", "name": "Source"}, listen_date="2026-01-01",
            ).record
            target = library.add_album(
                {"artist": "Artist", "name": "Target", "release_group_mbid": "target-group"},
                listen_date="2026-01-02",
            ).record
            with patch.object(session, "commit", wraps=session.commit) as commit:
                key = library.replace_catalog_metadata_for_refresh(source["album_key"], {
                    "artist": "Artist", "name": "Target", "release_group_mbid": "target-group",
                    "tracklist": [{"title": "Refreshed", "credits": [["New Producer", "producer"]]}],
                })
            commit.assert_called_once_with()

        with self.sessions() as session:
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            record = library.list_records()[key]
            self.assertEqual((key, record["id"]), (target["album_key"], target["id"]))
            self.assertEqual(record["listen_history"], ["2026-01-01", "2026-01-02"])
            self.assertIsNone(session.get(Album, source["id"]))
            fact = session.scalars(select(AlbumCreditFact)).one()
            self.assertEqual((fact.album_id, fact.person_name), (record["id"], "New Producer"))

    def test_credit_insert_failure_rolls_back_metadata_and_previous_facts(self):
        original_tracks = [{"title": "Original", "credits": [["Original Producer", "producer"]]}]
        with self.sessions() as session:
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            album_id = library.add_album({
                "artist": "Artist", "name": "Album", "tracklist": original_tracks,
            }).change.album_id
            original_fact = session.scalars(select(AlbumCreditFact)).one()
            persisted_fact = (original_fact.id, original_fact.person_name, original_fact.updated_at)
            self.assertEqual(original_fact.person_name, "Original Producer")

        with self.engine.begin() as connection:
            # Raise only after the old credit facts have been cleared.
            connection.exec_driver_sql("""
                CREATE TRIGGER reject_replacement_credit BEFORE INSERT ON album_credit_facts
                WHEN NEW.person_name = 'Rejected Producer' AND NOT EXISTS (
                    SELECT 1 FROM album_credit_facts WHERE album_id = NEW.album_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'injected credit projection failure');
                END
            """)

        with self.sessions() as session:
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            with self.assertLogs("backend.app.repositories.sqlite_state_repository", level="ERROR") as logs:
                with self.assertRaisesRegex(IntegrityError, "injected credit projection failure"):
                    library.patch_metadata(album_id, {
                        "tracklist": [{"title": "Changed", "credits": [["Rejected Producer", "producer"]]}],
                    })
            self.assertEqual(logs.records[0].getMessage(), "Credit fact rebuild failed for 1 albums (IntegrityError)")
            session.rollback()

        with self.sessions() as session:
            album = session.get(Album, album_id)
            self.assertEqual(album.metadata_json["tracklist"], original_tracks)
            fact = session.scalars(select(AlbumCreditFact)).one()
            self.assertEqual((fact.id, fact.person_name, fact.updated_at), persisted_fact)

    def test_import_cleanup_keeps_album_with_a_global_listen_or_membership(self):
        with self.sessions() as session:
            users = UserRepository(session)
            importer = users.ensure_default_user()
            other = users.create_user(slug="other", display_name="Other")
            library = AlbumLibrary(session, importer)
            timestamp = "2026-02-01T00:00:00Z"
            album_ids = [
                library.add_album({"artist": "Artist", "name": title}, listen_date=timestamp).record["id"]
                for title in ("Global listen", "Global membership", "Orphan")
            ]
            session.add_all([
                AlbumListen(user_id=other.id, album_id=album_ids[0], listened_at=timestamp),
                UserAlbum(user_id=other.id, album_id=album_ids[1], rating=7),
            ])
            import_row = import_session_repository.stage_session(
                session, user_id=importer.id, source="lastfm", status="completed", started_at=timestamp,
            )
            session.add_all(
                ImportedListeningEvent(
                    user_id=importer.id, import_session_id=import_row.id, album_id=album_id,
                    source="lastfm", artist="Artist", event_fingerprint=f"event-{album_id}",
                    listened_at=timestamp, match_status="processed_album_listen",
                )
                for album_id in album_ids
            )
            import_id, importer_id = import_row.id, importer.id
            session.commit()
            response = delete_import_session(session, importer_id, import_id)
            self.assertEqual(
                (response.deleted_events, response.deleted_listens, response.removed_user_albums, response.deleted_albums),
                (3, 3, 3, 1),
            )

        with self.sessions() as session:
            self.assertEqual(list(session.scalars(select(Album.id).order_by(Album.id))), album_ids[:2])
            self.assertEqual(session.scalars(select(AlbumListen.album_id)).one(), album_ids[0])
            self.assertEqual(session.scalars(select(UserAlbum.album_id)).one(), album_ids[1])

    def test_delete_import_with_more_album_ids_than_sqlite_can_bind_at_once(self):
        album_count = 520
        variable_limit = 512
        timestamp = "2026-02-02T00:00:00Z"
        with self.sessions() as session:
            user_id = UserRepository(session).ensure_default_user().id
            albums = [
                Album(album_key=f"Artist - Album {index}", artist="Artist", name=f"Album {index}")
                for index in range(album_count)
            ]
            session.add_all(albums)
            session.flush()
            import_row = import_session_repository.stage_session(
                session, user_id=user_id, source="lastfm", status="completed", started_at=timestamp,
            )
            import_id = import_row.id
            for album in albums:
                session.add_all([
                    UserAlbum(user_id=user_id, album_id=album.id),
                    AlbumListen(user_id=user_id, album_id=album.id, listened_at=timestamp),
                    ImportedListeningEvent(
                        user_id=user_id, import_session_id=import_id, album_id=album.id,
                        source="lastfm", artist="Artist", event_fingerprint=f"event-{album.id}",
                        listened_at=timestamp, match_status="processed_album_listen",
                    ),
                ])
            session.commit()

        with self.sessions() as session:
            self.limit_sqlite_variables(session, variable_limit)

            result = delete_import_session(session, user_id, import_id)

        self.assertEqual(
            (result.deleted_events, result.deleted_listens, result.removed_user_albums, result.deleted_albums),
            (album_count, album_count, album_count, album_count),
        )
        with self.sessions() as session:
            for model in (Album, AlbumListen, ImportedListeningEvent, ImportSession, UserAlbum):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 0, model.__name__)

    def test_candidate_reads_batch_keys_and_keep_all_same_profile_events(self):
        keys = [f"candidate-{index}" for index in range(520)]
        timestamp = "2026-03-01T00:00:00Z"
        with self.sessions() as session:
            users = UserRepository(session)
            user_id = users.ensure_default_user().id
            other_id = users.create_user(slug="other", display_name="Other").id
            first, second, foreign = (
                import_session_repository.stage_session(
                    session, user_id=owner, source=source, status="completed", started_at=timestamp,
                )
                for owner, source in ((user_id, "lastfm"), (user_id, "spotify_import"), (other_id, "lastfm"))
            )
            session.add_all(
                ImportedListeningEvent(
                    user_id=import_row.user_id, import_session_id=import_row.id, source=import_row.source,
                    artist="Artist", candidate_key=key, event_fingerprint=f"{import_row.id}-{key}",
                    listened_at=timestamp, match_status="raw",
                )
                for import_row, candidate_keys in ((first, keys), (second, [keys[0], "unselected"]), (foreign, keys))
                for key in candidate_keys
            )
            first_id, second_id = first.id, second.id
            session.commit()

        with self.sessions() as session:
            self.limit_sqlite_variables(session, 512)
            with patch.object(session, "commit", wraps=session.commit) as commit:
                rows = import_event_repository.rows_for_candidates(session, user_id, [*keys, keys[0]])
                self.assertEqual(import_event_repository.rows_for_candidates(session, user_id, []), [])
            commit.assert_not_called()
            self.assertCountEqual(
                [(row.user_id, row.import_session_id, row.candidate_key) for row in rows],
                [(user_id, first_id, key) for key in keys] + [(user_id, second_id, keys[0])],
            )

    def test_library_commit_survives_interruption_before_candidate_result(self):
        timestamp = "2026-03-01T00:00:00Z"
        with self.sessions() as session:
            user = UserRepository(session).ensure_default_user()
            row = import_session_repository.stage_session(
                session, user_id=user.id, source="lastfm", status="finalizing", started_at=timestamp,
            )
            session.add(ImportedListeningEvent(
                user_id=user.id, import_session_id=row.id, source="lastfm", candidate_key="candidate",
                listened_at=timestamp, artist="Artist", album="Album", match_status="raw",
                event_fingerprint="candidate-event",
            ))
            session.commit()

        def candidate():
            return AlbumCandidate(
                "candidate", "Artist", "Album", timestamp, [], 2,
                metadata={"artist": "Artist", "name": "Album", "tracklist": [{"title": "Track"}]},
                status="new_album",
            )

        with self.sessions() as session:
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            with patch.object(candidate_results.import_events, "record_candidate_result", side_effect=RuntimeError("interrupted")):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    candidate_results.apply_candidate_results(session, library, [candidate()])

        with self.sessions() as session:
            self.assertEqual(session.scalars(select(AlbumListen.listened_at)).one(), timestamp)
            row = session.scalars(select(ImportedListeningEvent)).one()
            self.assertEqual((row.match_status, row.album_id), ("raw", None))
            library = AlbumLibrary(session, UserRepository(session).ensure_default_user())
            candidate_results.apply_candidate_results(session, library, [candidate()])
            session.commit()

        with self.sessions() as session:
            self.assertEqual(session.scalars(select(AlbumListen.listened_at)).one(), timestamp)
            row = session.scalars(select(ImportedListeningEvent)).one()
            self.assertEqual((row.match_status, row.album_id), ("duplicate_listen", None))

    def test_snapshot_replaces_then_extends_history_for_shared_input_identity(self):
        with self.sessions() as session:
            user = UserRepository(session).ensure_default_user()
            library = AlbumLibrary(session, user)
            result = library.add_album(
                {"artist": "Artist", "name": "Canonical", "release_group_mbid": "group"},
                listen_date="2026-01-01",
            )
            album_id = result.change.album_id
            self.assertEqual(result.change.listens_added, ("2026-01-01",))
            library.set_feedback(album_id, rating=8, notes="Keep feedback")
            snapshot = AlbumStateRepository(session, user)
            snapshot.replace({
                "completed_albums": {
                    "Artist - Canonical": {
                        "release_group_mbid": "group",
                        "listen_history": ["2026-02-01", "2026-02-01"],
                    },
                    "Artist - Alternate": {
                        "release_group_mbid": "group",
                        "listen_history": ["2026-02-01", "2026-03-01"],
                    },
                },
            })

        with self.sessions() as session:
            user = UserRepository(session).ensure_default_user()
            completed = AlbumStateRepository(session, user).load()["completed_albums"]
            self.assertEqual(list(completed), ["Artist - Canonical"])
            record = completed["Artist - Canonical"]
            self.assertEqual(record["id"], album_id)
            self.assertEqual(record["listen_history"], ["2026-02-01", "2026-03-01"])
            self.assertEqual((record["rating"], record["notes"]), (8, "Keep feedback"))

    def test_bulk_reads_keep_profile_data_order_and_constant_statement_counts(self):
        with self.sessions() as session:
            users = UserRepository(session)
            user = users.ensure_default_user()
            other = users.create_user(slug="other", display_name="Other")
            library = AlbumLibrary(session, user)
            first = library.add_album({
                "artist": "Artist", "name": "Same Name", "release_group_mbid": "first-group",
                "_manual_input_identity": "manual-alias", "image_url": "https://example.test/cover.jpg",
                "local_image_path": "artwork/local.jpg", "tracklist": [{"title": "First"}],
                "listen_history": ["2026-01-03", "2026-01-01"],
            }).record
            second = library.add_album({
                "artist": "Artist", "name": "Same Name", "release_group_mbid": "second-group",
                "tracklist": [{"title": "Second"}],
            }).record
            library.set_tags(first["id"], ["cohesive"])
            library.set_feedback(first["id"], rating=9, notes="My notes")
            other_library = AlbumLibrary(session, other)
            other_library.add_listen(first["id"], "2026-01-02")
            other_library.set_feedback(first["id"], rating=3, notes="Another profile")

        small_state, small_state_statements, small_matches, small_match_statements = self.measure_reads()
        first_record = small_state["completed_albums"][first["album_key"]]
        second_record = small_state["completed_albums"][second["album_key"]]
        self.assertEqual(first_record["listen_history"], ["2026-01-01", "2026-01-03"])
        self.assertEqual((first_record["your_tags"], first_record["rating"], first_record["notes"]), (["cohesive"], 9, "My notes"))
        self.assertEqual(first_record["image_url"], "/media/artwork/local.jpg")
        self.assertEqual(first_record["remote_image_url"], "https://example.test/cover.jpg")
        self.assertNotIn("_manual_input_identity", first_record)
        self.assertEqual(second_record["listen_history"], [])
        match = small_matches[("artist", "same name")]
        self.assertEqual((match.album_id, match.record["tracklist"]), (second["id"], [{"title": "Second"}]))

        with self.sessions() as session:
            user_id = UserRepository(session).ensure_default_user().id
            albums = [
                Album(album_key=f"Other - Album {index:02}", artist="Other", name=f"Album {index:02}")
                for index in range(40)
            ]
            session.add_all(albums)
            session.flush()
            session.add_all(UserAlbum(user_id=user_id, album_id=album.id) for album in albums)
            session.commit()

        large_state, large_state_statements, large_matches, large_match_statements = self.measure_reads()
        self.assertEqual(len(large_state["completed_albums"]), 42)
        self.assertEqual(list(large_state["completed_albums"]), sorted(large_state["completed_albums"]))
        self.assertEqual(len(large_matches), 41)
        self.assertEqual((len(small_state_statements), len(large_state_statements)), (5, 5))
        self.assertEqual((len(small_match_statements), len(large_match_statements)), (1, 1))
        sql = large_match_statements[0].lower()
        for field in ("album_listens", "your_tags", "rating", "notes"):
            self.assertNotIn(field, sql)

        with self.sessions() as session:
            session.execute(text("UPDATE albums SET metadata_json = x'80' WHERE id = :id"), {"id": first["id"]})
            session.commit()
        with self.sessions() as session:
            state = AlbumStateRepository(session, UserRepository(session).ensure_default_user()).load()
            corrupt = state["completed_albums"][first["album_key"]]
            self.assertNotIn("tracklist", corrupt)
            self.assertEqual(corrupt["listen_history"], first_record["listen_history"])
            self.assertEqual(corrupt["image_url"], first_record["image_url"])
            self.assertEqual(corrupt["notes"], first_record["notes"])

    def measure_reads(self):
        statements = []

        def collect(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        with self.sessions() as session:
            user = UserRepository(session).ensure_default_user()
            event.listen(self.engine, "before_cursor_execute", collect)
            try:
                state = AlbumStateRepository(session, user).load()
                state_statements = statements.copy()
                statements.clear()
                matches = load_existing_albums(AlbumLibrary(session, user))
                return state, state_statements, matches, statements.copy()
            finally:
                event.remove(self.engine, "before_cursor_execute", collect)
