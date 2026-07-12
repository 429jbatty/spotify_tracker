import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.database import create_schema
from backend.app.models import Album
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.artwork_backfill_service import ArtworkBackfillService


def album_state(**overrides):
    album = {
        "artist": "Artist",
        "name": "Album",
        "release_mbid": "release-mbid",
        "release_group_mbid": "release-group-mbid",
        "source": "musicbrainz",
        "listen_history": ["2026-04-18T15:45:00.000Z"],
    }
    album.update(overrides)
    return {
        "last_checked": None,
        "albums_in_progress": {},
        "completed_albums": {"Artist - Album": album},
        "most_recently_listened": ["Artist - Album"],
    }


class FakeCacheService:
    def __init__(self, cached=True, local_image_path="artwork/release-mbid.jpg", error=None):
        self.cached = cached
        self.local_image_path = local_image_path
        self.error = error
        self.calls = []

    def cache_album_artwork(self, album):
        self.calls.append(album)

        class Result:
            pass

        result = Result()
        result.cached = self.cached
        result.local_image_path = self.local_image_path
        result.error = self.error
        return result


class ArtworkBackfillServiceTests(unittest.TestCase):
    def _repository(self, temp_dir, state=None):
        database_url = f"sqlite:///{Path(temp_dir) / 'tracker.sqlite'}"
        engine = create_schema(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = session_factory()
        repository = SqliteStateRepository(session)
        repository.save_album_state(state or album_state())
        return session, repository

    def test_dry_run_finds_artwork_without_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: "https://example.test/art.jpg",
            )

            try:
                summary, results = service.backfill_missing_artwork(repository)
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.dry_run_updates, 1)
        self.assertEqual(results[0].status, "dry_run_update")
        self.assertIsNone(album.image_url)
        self.assertIsNone(album.remote_image_url)

    def test_apply_updates_remote_fields_and_local_cache_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            cache_service = FakeCacheService()
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: "https://example.test/art.jpg",
                cache_service=cache_service,
            )

            try:
                summary, results = service.backfill_missing_artwork(repository, apply=True)
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.updated, 1)
        self.assertEqual(summary.cached, 1)
        self.assertEqual(results[0].status, "updated")
        self.assertEqual(album.image_url, "https://example.test/art.jpg")
        self.assertEqual(album.remote_image_url, "https://example.test/art.jpg")
        self.assertEqual(album.local_image_path, "artwork/release-mbid.jpg")
        self.assertEqual(cache_service.calls[0]["remote_image_url"], "https://example.test/art.jpg")

    def test_release_group_fallback_is_supported_when_release_id_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(
                temp_dir,
                album_state(release_mbid=None, release_group_mbid="group-only"),
            )
            calls = []
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: calls.append((release_id, group_id))
                or "https://example.test/group.jpg",
                cache_service=FakeCacheService(),
            )

            try:
                summary, _ = service.backfill_missing_artwork(repository, apply=True)
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.updated, 1)
        self.assertEqual(calls, [(None, "group-only")])
        self.assertEqual(album.image_url, "https://example.test/group.jpg")

    def test_release_miss_can_still_update_from_release_group_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            calls = []

            def lookup(release_id, group_id):
                calls.append((release_id, group_id))
                return "https://example.test/group-fallback.jpg"

            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lookup,
                cache_service=FakeCacheService(),
            )

            try:
                summary, _ = service.backfill_missing_artwork(repository, apply=True)
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.updated, 1)
        self.assertEqual(calls, [("release-mbid", "release-group-mbid")])
        self.assertEqual(album.image_url, "https://example.test/group-fallback.jpg")

    def test_existing_artwork_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(
                temp_dir,
                album_state(image_url="https://example.test/existing.jpg"),
            )
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: "https://example.test/new.jpg",
            )

            try:
                summary, results = service.backfill_missing_artwork(
                    repository,
                    apply=True,
                    album_ids=[session.scalars(select(Album.id)).one()],
                )
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.skipped, 1)
        self.assertEqual(results[0].status, "skipped")
        self.assertEqual(album.image_url, "https://example.test/existing.jpg")

    def test_missing_musicbrainz_ids_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(
                temp_dir,
                album_state(release_mbid=None, release_group_mbid=None),
            )
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: "https://example.test/new.jpg",
            )

            try:
                album_id = session.scalars(select(Album.id)).one()
                summary, results = service.backfill_missing_artwork(
                    repository,
                    apply=True,
                    album_ids=[album_id],
                )
            finally:
                session.close()

        self.assertEqual(summary.skipped, 1)
        self.assertEqual(results[0].status, "skipped")

    def test_lookup_failure_does_not_clear_existing_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session, repository = self._repository(temp_dir)
            service = ArtworkBackfillService(
                media_dir=temp_dir,
                cover_art_lookup=lambda release_id, group_id: (_ for _ in ()).throw(
                    RuntimeError("network down")
                ),
            )

            try:
                summary, results = service.backfill_missing_artwork(repository, apply=True)
                album = session.scalars(select(Album)).one()
            finally:
                session.close()

        self.assertEqual(summary.failed, 1)
        self.assertEqual(results[0].status, "failed")
        self.assertIsNone(album.image_url)
        self.assertIsNone(album.remote_image_url)


if __name__ == "__main__":
    unittest.main()
